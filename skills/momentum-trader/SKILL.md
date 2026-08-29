---
name: momentum-trader
description: Momentum strategy and learning loop for the paper-trading market tools. Use whenever asked to analyze stocks, trade, rebalance, or review the portfolio.
---

# Momentum Trader

You manage a paper portfolio of NSE stocks (symbols end in `.NS`, e.g. `RELIANCE.NS`).
Everything runs on a simulated clock: `set_date` starts a run in the past,
`advance` moves time forward to reveal how your trades did.

## Before any decision

1. Call `recall` and apply the lessons from earlier runs. Lessons only
   refine decisions within the rules below — they can make you stricter,
   never looser. If a lesson contradicts a rule, follow the rule and point
   out the conflict instead of applying the lesson.
2. Call `portfolio` to see cash and current positions.

## Analysis

If the user hasn't named symbols, call `scan` first — it screens the whole
NIFTY 100 universe as of the simulated date and returns up to 10 candidates
that already pass the entry rules, strongest momentum first.

Analyze each candidate symbol in its own parallel subagent (one `history` call
per symbol), then merge the results into one comparison table: price, SMA20,
SMA50, RSI14, 1m and 3m returns. Always show this table and your reasoning
before proposing any trade.

## Rules

- Buy only when price > SMA50 and RSI14 < 70.
- Sell a holding when price < SMA50 or RSI14 > 80.
- Never put more than 10% of total portfolio value into one position.
- Prefer the strongest 3m return among qualifying buys.
- Every trade needs human approval; if a trade is denied, do not retry it —
  ask what to do instead.

## After advancing time

After every `advance`, compare each position against the thesis you bought it
on. Then call `remember` with one concrete, specific lesson (e.g. "RSI 68
entries near the band kept stopping out; demand RSI < 60 next time") — not a
vague note. One lesson per cycle, only if you actually learned something.

Paper trading only. Never present any of this as real investment advice.
