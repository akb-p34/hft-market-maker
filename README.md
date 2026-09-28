# HFT market maker (Stevens HFT Competition 2025)

Team **Spread Snipers** placed **2nd of 60+ teams** at the 2025 Stevens High Frequency Trading Competition with this market-making code.

The team:

- Sharif Haason
- Scott Henriquez
- Akbar Pathan
- Saugat Shrestha

All four of us wrote this code together.

## What it does

The bot is a market maker. It posts a buy order a little below the market and a sell order a little above it, over and over, and earns the gap between them when both sides fill. The risk is inventory: if the price runs one way, the bot ends up holding shares that are losing money. Most of the code is about deciding where to quote and how much to show so that inventory stays small.

It runs on SHIFT, the simulated exchange built at Stevens, which has a live limit order book that every team's bot trades against.

## How the strategy works

There are two pieces.

**`avellaneda_stoikov.py`** follows the Avellaneda-Stoikov model (2008), the standard textbook setup for a market maker with inventory risk:

1. Estimate short-term volatility from recent log returns of sampled prices.
2. Estimate how fast liquidity thins out away from the best price. For each side of the book it fits log(size) against distance from the best price over 20 levels. The slope is `k`.
3. Shift the fair price against inventory. The reservation price is `mid - q * gamma * sigma^2 * (T - t)`, where `q` is inventory in lots and `gamma` is risk aversion. Long inventory pulls both quotes down so the bot sells more easily, and short inventory does the opposite. The shift shrinks as the session end gets closer.
4. Set each side's distance from the reservation price with `(2 / gamma) * ln(1 + gamma / k)`, so a thin book gets a wider quote.
5. Post a 10-lot limit buy and sell at those prices and repeat.

**`run.py`** is the main loop as we last saved it. It runs one thread per symbol and waits 30 minutes at the open so price samples can build up. Then, every cycle:

- It computes the volume-weighted average price of the top 5 levels on each side and measures how far that sits from the best bid or ask. If the gap on a side is bigger than a set threshold, the bot skips quoting that side.
- It starts one step inside the best bid and ask, then shifts each quote by that side's gap. The step is 1 to 3 cents, scaled by volatility.
- It sizes orders from inventory and order book imbalance. If we are short, the buy size goes up, and if we are long, the sell size goes up. Imbalance in the book scales both. Sizes are capped at 10 lots.
- Orders rest for 30 seconds, then get cancelled and re-quoted.
- Every 20 minutes the bot flattens its position, and at the end of the session it cancels everything and liquidates.

`run.py` doesn't call `avellaneda_stoikov.py`. The A-S model has its own quoting loop (`run_stoikov_strategy`), and we traded with more than one of these files during the competition.

`run.py` also keeps other versions of the quoting logic we tried (a moving-average quote, a MACD trend filter, and a Bollinger band spread capture). The main loop doesn't call them, but they show how the approach changed.

## Files

| File | What it is |
|---|---|
| `avellaneda_stoikov.py` | The Avellaneda-Stoikov quoting model: volatility, order book depth `k`, reservation price, spreads |
| `run.py` | Connects to SHIFT, starts one quoting thread per symbol, logs market data and orders, liquidates at the end |
| `config.example.ini` | The settings `run.py` reads, with placeholders instead of real login details |
| `REDACTIONS.md` | What was removed or left out for this public copy |

## Can I run it?

Not on your own. The code talks to SHIFT through Stevens' `shift` Python client, and SHIFT isn't public. This repository is for reading, not running.

If you do have SHIFT access, copy `config.example.ini` to `config.ini`, fill in your own login and settings (the values in the example file are placeholders, not the settings we used in the competition), and run `python run.py`. Keep `config.ini` out of version control; `.gitignore` already excludes it.

## Afterward: QF 302

Later that semester, Akbar and a different team rebuilt a simpler version of this quoting model for the QF 302 (Financial Market Microstructure and Trading Strategies) final project. Because SHIFT isn't available outside class, they ran it on public 1-minute Yahoo Finance data for AAPL, MSFT and SPY and compared it with a moving-average crossover strategy and with buy-and-hold. That course code isn't included here.

## Sharing

Akbar published this copy with the team credited above. All rights stay with its four authors, so there's no open-source license.
