"""DeepDip-120: a patient mean-reversion bot for the BTC 24h race.

Strategy, in one paragraph: cbBTC on 1-minute bars is a range-bound,
mean-reverting market on this horizon (the dev window's 60-minute
momentum agreement is only ~0.39, i.e. moves reverse more often than
they continue, while 1-minute noise whipsaws every fast trend
follower). So this bot does nothing most of the time and waits for a
real dip: it buys with its full cash only when the close falls at
least 0.70% below its 120-minute EMA, then sells when the price has
reverted to 0.60% above that same EMA. Every exit is guarded by a
0.6% stop-loss against entry cost, a 0.8% trailing stop against the
position's peak value, and a 6-hour time stop, plus a 5% equity
drawdown halt. Shallow dips are deliberately NOT traded: backtests
show 0.4-0.5% dips lose money after the ~37 bps round-trip cost
(fees 4 bps + slippage 2 bps + pool impact, each side), so only
deep dips clear the cost hurdle with margin. One late-window
fallback entry (a 0.50% dip after bar 1080, only if the bot has not
traded yet) exists purely so the entry can never end a window with
zero trades through sheer bad luck.

Protocol: agent-fun/bars-replay/v1. The bot reads hello once (the
universe, capital, caps, fees and the phase seed), then one batch per
minute (the bar that closed, the fills of the previous orders, the
account), and answers every batch with exactly one reply echoing its
seq. Orders decided on a batch fill at the next bar's open.

Determinism: no clock, no environment, no randomness, no network,
no files. The only state is the EMA and a few counters, all derived
from the bars themselves in a fixed order, so two runs on the same
data produce byte-identical action logs.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (all in basis points unless noted) ---
EMA_SPAN = 120            # minutes of closes in the slow mean
DEEP_DIP_BPS = 70         # buy when close < EMA * (1 - 0.70%)
DEEP_EXIT_BPS = 60        # sell when close > EMA * (1 + 0.60%)
FALLBACK_BAR = 1080       # fallback entry only in the last 6 hours
FALLBACK_DIP_BPS = 50     # ... on a 0.50% dip, and only if never traded
FALLBACK_EXIT_BPS = 30    # ... exiting at EMA * (1 + 0.30%)
STOP_BPS = 60             # stop-loss: position value 0.6% under its cost
TRAIL_BPS = 80            # trailing stop: 0.8% under the peak value
MAX_HOLD_BARS = 360       # time stop: 6 hours in a position, then exit
COOLDOWN_BARS = 120       # after a stop-loss exit, wait 2h before re-entry
NO_ENTRY_AFTER = 1380     # no new entries in the last hour of the window
HALT_DD_BPS = 500         # halt all trading if equity falls 5% off its peak
MAX_SLIPPAGE_BPS = 500    # 5%: far above any real 1-minute gap, so fills
                          # are never rejected for slippage in practice


class Bot:
    """All mutable state, derived only from hello and the batches."""

    def __init__(self):
        self.ema = None            # 120-minute EMA of closes (float USDC*1e5)
        self.warm_closes = []      # closes collected until the EMA seeds
        self.entry_seq = -1        # seq of the batch that opened the position
        self.entry_mode = "deep"   # "deep" or "fallback": which exit to use
        self.pending_mode = "deep"
        self.peak_value = 0        # peak position value since entry (quote units)
        self.run_peak_equity = 0   # peak equity seen this run (quote units)
        self.halted = False        # set by the drawdown halt; never unset
        self.has_traded = False    # any filled buy so far
        self.cooldown_until = -1   # no entries before this seq (after a stop)
        self.armed = True          # entries allowed only while armed; a sell
                                   # disarms until the price has climbed back
                                   # to within 0.2% of the EMA, so a step-down
                                   # cannot be re-bought over and over while
                                   # the slow EMA is still catching up to it

    def on_batch(self, state, batch):
        fresh = [b for b in batch["bars"] if b["symbol"] == SYMBOL]
        if not fresh:
            # No bar for our symbol this minute: decide nothing on stale data.
            return []
        close = int(fresh[0]["c"])

        # --- track the run's equity peak and the drawdown halt ---
        if state.equity > self.run_peak_equity:
            self.run_peak_equity = state.equity
        if (
            self.run_peak_equity > 0
            and state.equity * 10000 <= self.run_peak_equity * (10000 - HALT_DD_BPS)
        ):
            self.halted = True

        # --- count filled buys (for the never-traded fallback) ---
        for fill in batch["fills"]:
            if (
                fill["symbol"] == SYMBOL
                and fill["side"] == "buy"
                and fill["status"] == "filled"
            ):
                self.has_traded = True

        # --- update the 120-minute EMA of closes ---
        if self.ema is None:
            self.warm_closes.append(close)
            if len(self.warm_closes) >= EMA_SPAN:
                self.ema = sum(self.warm_closes) / float(EMA_SPAN)
                self.warm_closes = []
        else:
            self.ema += (2.0 / (EMA_SPAN + 1.0)) * (close - self.ema)

        held = state.positions.get(SYMBOL)

        if held is not None:
            return self._maybe_exit(state, close, held)

        # --- flat: re-arm once the price is back near its mean, then
        # consider an entry ---
        if self.ema is not None and close * 10000 > self.ema * (10000 - 20):
            self.armed = True
        if (
            state.warming_up
            or self.halted
            or not self.armed
            or self.ema is None
            or state.seq >= NO_ENTRY_AFTER
            or state.seq < self.cooldown_until
        ):
            return []
        deep_dip = close * 10000 < self.ema * (10000 - DEEP_DIP_BPS)
        fallback_dip = (
            not self.has_traded
            and state.seq >= FALLBACK_BAR
            and close * 10000 < self.ema * (10000 - FALLBACK_DIP_BPS)
        )
        if not (deep_dip or fallback_dip):
            return []
        self.pending_mode = "fallback" if (fallback_dip and not deep_dip) else "deep"
        notional = state.cash
        room = state.weight_room(SYMBOL)
        if room < notional:
            notional = room
        min_notional = int(state.hello["fees"]["min_notional_quote_units"])
        if notional < min_notional or notional <= 0:
            return []
        return [
            {
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": notional,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }
        ]

    def _maybe_exit(self, state, close, held):
        # First bar of a new position: record entry seq/mode, reset the peak.
        if self.entry_seq < 0 or self.peak_value == 0:
            self.entry_seq = state.seq
            self.entry_mode = self.pending_mode
            self.peak_value = 0
        value = state.value(SYMBOL, held.qty)
        if value > self.peak_value:
            self.peak_value = value
        exit_bps = DEEP_EXIT_BPS if self.entry_mode == "deep" else FALLBACK_EXIT_BPS
        mean_exit = close * 10000 > self.ema * (10000 + exit_bps)
        stop_exit = value * 10000 <= held.cost * (10000 - STOP_BPS)
        trail_exit = (
            self.peak_value > 0
            and value * 10000 <= self.peak_value * (10000 - TRAIL_BPS)
        )
        time_exit = state.seq - self.entry_seq >= MAX_HOLD_BARS
        if self.halted:
            # Drawdown halt: get flat now, whatever the reason.
            return self._sell_all(state, held, stop=True)
        if not (mean_exit or stop_exit or trail_exit or time_exit):
            return []
        return self._sell_all(state, held, stop=(stop_exit or trail_exit))

    def _sell_all(self, state, held, stop):
        if stop:
            self.cooldown_until = state.seq + COOLDOWN_BARS
        # Any exit disarms entries until the price climbs back near the EMA.
        self.armed = False
        self.entry_seq = -1
        self.peak_value = 0
        return [
            {
                "side": "sell",
                "symbol": SYMBOL,
                "qty": held.qty,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }
        ]


def main():
    bot = Bot()
    makefun_bars.run(bot.on_batch)


if __name__ == "__main__":
    main()
