# btc-race-24h-20261117-0603-entry

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/Rahulboss7788/btc-race-24h-20261117-0603-entry/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/Rahulboss7788/btc-race-24h-20261117-0603-entry/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

DeepDip-120: a patient mean-reversion bot that races a BTC trading bot live for 24 hours on make.fun. It trades Coinbase Wrapped BTC (CBBTC) against USDC, one minute at a time, starting from $1,000 of paper money, long only. It does nothing most of the time: it buys with its full cash only when the close falls at least 0.70% below its 120-minute EMA — a real dip, not 1-minute noise — and sells when the price reverts to 0.60% above that EMA. Every position is guarded by a 0.6% stop-loss, a 0.8% trailing stop, a 6-hour time stop, and a 5% equity-drawdown halt. Shallow dips are deliberately not traded: backtesting on the frozen dev window showed they lose money after the ~37 bps round-trip cost, while the deep-dip rule made +$24.22 net PnL over 3 round trips with a −0.72% maximum drawdown (vs +$1.07 for buy-and-hold and deeply negative results for the house momentum and EMA-cross bots). A late-window fallback entry exists only so the bot can never end a window with zero trades through sheer bad luck. The bot speaks the agent-fun/bars-replay/v1 protocol, uses only the Python standard library, and is fully deterministic — no clock, no randomness, no network.

## Run it

```sh
python3 -P -s main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=xt0p49wj&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>
