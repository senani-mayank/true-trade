"""Paper-trading tool server for TrueForge, MCP over streamable HTTP.

All market data comes from yfinance (free, delayed). All money is fake.
The clock is simulated: set_date() jumps to a past date, advance() moves
forward, so you can trade on old data and then see how it played out.

Run the server:  python market_mcp.py          (http://127.0.0.1:8765/mcp)
Self-check:      python market_mcp.py check
"""

import json
import os
import sys
from datetime import date, timedelta

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
PORTFOLIO = os.path.join(HERE, "portfolio.json")
MEMORY = os.path.join(HERE, "memory.md")
TRADES = os.path.join(HERE, "trades.log")
START_CASH = 1_000_000.0  # ten lakh virtual rupees

READ = ToolAnnotations(readOnlyHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)

mcp = MCPServer("market")


def load(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def sim_today():
    return load(STATE, {"today": str(date.today())})["today"]


def closes(symbol, days=300):
    """Daily closing prices up to and including the simulated date."""
    import yfinance as yf  # slow import, only needed when data is asked for

    end = date.fromisoformat(sim_today()) + timedelta(days=1)  # yf end is exclusive
    df = yf.download(symbol, start=str(end - timedelta(days=days)), end=str(end),
                     progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise ValueError("no data for %s (NSE symbols need .NS, e.g. RELIANCE.NS)" % symbol)
    close = df["Close"]
    if close.ndim > 1:  # newer yfinance returns one column per ticker
        close = close.iloc[:, 0]
    return close.dropna()


def last_price(symbol):
    return float(closes(symbol, days=15).iloc[-1])


def rsi14(close):
    change = close.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / 14).mean()
    loss = -change.clip(upper=0).ewm(alpha=1 / 14).mean()
    return float((100 - 100 / (1 + gain / loss)).iloc[-1])


def apply_buy(p, symbol, qty, price):
    """Pure portfolio math so it can be tested without the network."""
    if qty <= 0:
        return "error: qty must be a positive number of shares"
    cost = qty * price
    if cost > p["cash"]:
        return "error: need %.2f but only %.2f cash available" % (cost, p["cash"])
    pos = p["positions"].get(symbol, {"qty": 0, "avg_cost": 0.0})
    pos["avg_cost"] = (pos["avg_cost"] * pos["qty"] + cost) / (pos["qty"] + qty)
    pos["qty"] += qty
    p["positions"][symbol] = pos
    p["cash"] -= cost
    return "bought %d %s at %.2f, cash left %.2f" % (qty, symbol, price, p["cash"])


def apply_sell(p, symbol, qty, price):
    pos = p["positions"].get(symbol)
    if qty <= 0:
        return "error: qty must be a positive number of shares"
    if pos is None or pos["qty"] < qty:
        held = pos["qty"] if pos else 0
        return "error: you hold %d %s, cannot sell %d" % (held, symbol, qty)
    pnl = (price - pos["avg_cost"]) * qty
    pos["qty"] -= qty
    if pos["qty"] == 0:
        del p["positions"][symbol]
    p["cash"] += qty * price
    return "sold %d %s at %.2f, realised P&L %+.2f, cash now %.2f" % (
        qty, symbol, price, pnl, p["cash"])


def log_trade(line):
    with open(TRADES, "a") as f:
        f.write("[%s] %s\n" % (sim_today(), line))


def valued_portfolio():
    p = load(PORTFOLIO, {"cash": START_CASH, "positions": {}})
    out = {"date": sim_today(), "cash": round(p["cash"], 2), "positions": [], "total": p["cash"]}
    for symbol, pos in p["positions"].items():
        price = last_price(symbol)
        value = price * pos["qty"]
        out["positions"].append({
            "symbol": symbol, "qty": pos["qty"],
            "avg_cost": round(pos["avg_cost"], 2), "price": round(price, 2),
            "pnl": round((price - pos["avg_cost"]) * pos["qty"], 2),
        })
        out["total"] += value
    out["total"] = round(out["total"], 2)
    return out


@mcp.tool(annotations=WRITE)
def set_date(day: str) -> str:
    """Start (or restart) the simulation on a past date (YYYY-MM-DD). Resets the portfolio to fresh cash."""
    if date.fromisoformat(day) > date.today():
        return "error: pick a date in the past"
    save(STATE, {"today": day})
    save(PORTFOLIO, {"cash": START_CASH, "positions": {}})
    return "simulation reset: today is %s, cash %.0f" % (day, START_CASH)


@mcp.tool(annotations=WRITE)
def advance(days: int) -> dict:
    """Move the simulated clock forward N days and revalue the portfolio, revealing how the trades did."""
    try:
        new_day = date.fromisoformat(sim_today()) + timedelta(days=days)
        if new_day > date.today():
            return {"error": "cannot advance past the real today"}
        save(STATE, {"today": str(new_day)})
        return valued_portfolio()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(annotations=READ)
def history(symbol: str) -> dict:
    """Price snapshot with simple indicators as of the simulated date. NSE symbols need .NS, e.g. RELIANCE.NS."""
    try:
        close = closes(symbol)
        price = float(close.iloc[-1])
        return {
            "date": sim_today(), "symbol": symbol, "price": round(price, 2),
            "sma20": round(float(close.rolling(20).mean().iloc[-1]), 2),
            "sma50": round(float(close.rolling(50).mean().iloc[-1]), 2),
            "rsi14": round(rsi14(close), 1),
            "return_1m": round(price / float(close.iloc[-22]) - 1, 4),
            "return_3m": round(price / float(close.iloc[-64]) - 1, 4),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(annotations=READ)
def portfolio() -> dict:
    """Cash, positions and unrealised P&L, valued at the simulated date."""
    try:
        return valued_portfolio()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(annotations=WRITE)
def buy(symbol: str, qty: int) -> str:
    """Buy shares at the simulated date's closing price. Paper money only."""
    try:
        price = last_price(symbol)
    except Exception as e:
        return "error: " + str(e)
    p = load(PORTFOLIO, {"cash": START_CASH, "positions": {}})
    result = apply_buy(p, symbol, qty, price)
    if not result.startswith("error"):
        save(PORTFOLIO, p)
        log_trade(result)
    return result


@mcp.tool(annotations=WRITE)
def sell(symbol: str, qty: int) -> str:
    """Sell shares at the simulated date's closing price. Paper money only."""
    try:
        price = last_price(symbol)
    except Exception as e:
        return "error: " + str(e)
    p = load(PORTFOLIO, {"cash": START_CASH, "positions": {}})
    result = apply_sell(p, symbol, qty, price)
    if not result.startswith("error"):
        save(PORTFOLIO, p)
        log_trade(result)
    return result


@mcp.tool(annotations=WRITE)
def remember(lesson: str) -> str:
    """Save one lesson learned from a trade outcome, for future runs to build on."""
    with open(MEMORY, "a") as f:
        f.write("- [%s] %s\n" % (sim_today(), lesson.strip()))
    return "noted"


@mcp.tool(annotations=READ)
def recall() -> str:
    """Read every lesson saved so far. Do this before making any trading decision."""
    if not os.path.exists(MEMORY):
        return "no lessons saved yet"
    with open(MEMORY) as f:
        return f.read()


def check():
    """Offline self-check of the portfolio math and indicators."""
    p = {"cash": 2000.0, "positions": {}}
    assert apply_buy(p, "X", 0, 10).startswith("error")
    assert apply_buy(p, "X", 300, 10).startswith("error")  # too expensive
    apply_buy(p, "X", 50, 10)
    apply_buy(p, "X", 50, 20)
    assert p["positions"]["X"] == {"qty": 100, "avg_cost": 15.0}
    assert p["cash"] == 500.0
    assert apply_sell(p, "X", 200, 20).startswith("error")
    assert apply_sell(p, "Y", 1, 20).startswith("error")
    assert "P&L +500.00" in apply_sell(p, "X", 100, 20)
    assert p == {"cash": 2500.0, "positions": {}}

    import pandas as pd
    up = pd.Series(range(1, 61), dtype=float)
    assert rsi14(up) > 90  # straight uptrend => extreme RSI
    assert rsi14(up.iloc[::-1].reset_index(drop=True)) < 10
    print("all checks passed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check()
    else:
        mcp.run(transport="streamable-http", port=8765)
