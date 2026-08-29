# true-trade

A paper-trading agent for NSE stocks that runs on [TrueForge](https://github.com/truefoundry/trueforge),
built for The Agent Harness Hackathon (TF-007). It analyzes stocks with free
yfinance data, trades virtual money on a simulated clock, asks a human before
every trade, and writes down lessons so the next run is smarter.

No broker, no API costs, no real money. The whole tool layer is one Python file.

## How it works

```
TrueForge (agent loop, approvals, skill, subagents)
   │  MCP over HTTP
   ▼
market_mcp.py ── yfinance (prices, free)
   ├─ state.json      simulated "today"
   ├─ portfolio.json  virtual cash + positions
   ├─ memory.md       lessons the agent saved
   └─ trades.log      every fill
```

The clock is simulated: `set_date` starts a run on any past date, the agent
trades on the data that existed *up to that day*, then `advance` moves time
forward and reveals how the trades actually did. After each reveal the agent
saves one lesson with `remember`, and every new run starts by reading them
back with `recall` — so it visibly learns across cycles.

### The tools (all in `market_mcp.py`)

| Tool | What it does | Needs approval |
|---|---|---|
| `set_date` | start/reset the simulation on a past date | yes |
| `history` | price + SMA20/50, RSI14, 1m/3m returns as of the sim date | no |
| `portfolio` | cash, positions, unrealised P&L | no |
| `buy` / `sell` | trade at the sim date's closing price | **yes** |
| `advance` | move the clock forward, revalue everything | no |
| `remember` / `recall` | save / read lessons across runs | no |

## How it uses TrueForge

- **MCP connector** — the trading tools are a streamable-HTTP MCP server that
  TrueForge discovers, schema and all. Nothing is hardcoded into a prompt.
- **Human approval checkpoints** — `buy`, `sell` and `set_date` are marked
  destructive, so the harness pauses with Allow/Deny before any of them run.
  The agent can be stopped before it does damage; deny it and it asks what to
  do instead of retrying.
- **Skill** — the strategy lives in `skills/momentum-trader/SKILL.md`, loaded
  by TrueForge from this repo on demand (git-backed skill, read inside the
  sandbox). Change the strategy with a PR, not a redeploy.
- **Dynamic subagents** — with several candidate symbols, the harness fans the
  per-symbol analysis out to parallel subagents and merges only their results
  back into the main context.
- **The agent itself** is a saved TrueForge agent (model + instructions +
  connector + skill + approval config), created through the harness API.

## Setup

Needs Python 3.10+, Node 22+, and any model API key (we used OpenRouter's free tier).

```bash
git clone https://github.com/senani-mayank/true-trade && cd true-trade
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python market_mcp.py check     # offline self-test
.venv/bin/python market_mcp.py &         # tool server on http://127.0.0.1:8765/mcp
npx @truefoundry/trueforge@latest        # TrueForge on http://localhost:8790
```

Then in TrueForge (`http://localhost:8790`):

1. **Settings → Models** — add your provider (custom/OpenAI-compatible works,
   e.g. base URL `https://openrouter.ai/api/v1` + your key + a tool-calling model).
2. **Settings → Connectors → Add MCP Server** — URL `http://127.0.0.1:8765/mcp`, no auth.
3. **Settings → Skills** — this repo's URL, path `skills/momentum-trader`, ref `main`.
4. **Create an agent** — attach the connector and the skill, enable the
   sandbox and dynamic subagents, require approval for `buy`, `sell`, `set_date`.
   The instructions we used are in [`agent.md`](agent.md).

Try: *"Start a simulation on 2026-03-02, analyze RELIANCE.NS, TCS.NS,
HDFCBANK.NS and INFY.NS, and trade whatever qualifies. Then advance 30 days,
review the results and save a lesson."*

## Demo

[Demo video (~3 min)](TODO_VIDEO_LINK)

## Qodo Code Review Evidence

Every substantive change in this repo went through a pull request reviewed by
Qodo Merge before merging.

- Representative PR: [#1 — the tool server](https://github.com/senani-mayank/true-trade/pull/1).
  Qodo surfaced 8 findings, several of them real correctness bugs: the sim
  clock could move backward, trades could execute on today's unfinished
  close, and (High severity) the price lookup raced against clock changes.
  We fixed 7 across follow-up commits on the PR and dismissed 1 in the Qodo
  thread with a reason (trades.log is a demo convenience log, not the source
  of truth — portfolio.json is); Qodo marked the dismissal and its follow-up
  review of the final code came back clean.
- [#2 — the strategy skill](https://github.com/senani-mayank/true-trade/pull/2):
  Qodo caught that the skill let remembered lessons *override* the hard risk
  rules — a genuinely good catch for an agent that learns. Fixed so lessons
  can only make the agent stricter, never looser; the re-review reported
  zero bugs.
- Full PR history with reviews, fixes and decisions: [closed PRs](https://github.com/senani-mayank/true-trade/pulls?q=is%3Apr+is%3Aclosed)

## Disclosure

AI coding assistants were used during development, as permitted by the
hackathon rules. All code was reviewed, tested and is understood by the
participant. This is a simulation for demonstration purposes only — nothing
here is investment advice.
