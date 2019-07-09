import numpy as np
import pandas as pd

from trader.util import Log
from trader.util.stats import Emse, HoltEma


class ExecutionStrategy:
    def __init__(
        self,
        size,
        variance_hl,
        trend_hl,
        accel_hl,
        trend_cutoff,
        min_edge_to_enter,
        min_edge_to_close,
        warmup_data,
    ):
        self.size = size
        # Does it make sense to replace with something else? (like % of takes that are buys)
        self.trend_estimator = HoltEma(trend_hl, accel_hl)
        self.trend_cutoff = trend_cutoff
        self.min_edge_to_enter = min_edge_to_enter
        self.min_edge_to_close = min_edge_to_close

        warmup_mvmts = warmup_data.xs("price", axis=1, level=1).diff()[1:]
        mse = (warmup_mvmts ** 2).mean()
        self.mvmt_variance = Emse(variance_hl, mse)
        for _, mvmt in warmup_mvmts.iloc[-4 * accel_hl :].iterrows():
            self.trend_estimator.step(mvmt)

        self.prev_mids = warmup_data.xs("price", axis=1, level=1).iloc[-1]

        if not self.mvmt_variance.ready:
            Log.warn(
                "Insufficient warmup data for execution strategy. \
                    Will warm up (slowly) in real time."
            )
        else:
            Log.info("Execution strategy initialized and warm.")

    def tick(self, positions, bids, asks, fairs, fees):
        """Takes fair as Gaussian, positions in base currency.
        Returns orders in base currency (negative size indicates sell).

        Since our fair estimate may have skewed uncertainty, it may be the case that
        a price change for one trading pair causes us to desire positions in other
        pairs. Therefore get_orders needs to consider the entire set of fairs and
        bid/asks at once.

        TODO: generalize to multiple quotes
        TODO: use books instead of just the best bid/ask price
        """
        mids = (bids + asks) / 2  # Use mid price for target position value calculations.

        # Update trend and movement history
        if self.prev_mids is None:
            self.prev_mids = mids
        mvmt = mids - self.prev_mids
        self.prev_mids = mids
        self.mvmt_variance.step(mvmt)
        trend = self.trend_estimator.step(mvmt)
        if not self.mvmt_variance.ready:
            return pd.Series(0, index=mids.index)

        z_edge = (fairs.mean - mids) / fairs.stddev
        z_trend = trend / self.mvmt_variance.stderr
        target_position_values = z_edge * self.size
        pair_positions = positions[[(ep.exchange_id, ep.base) for ep in mids.index]].set_axis(
            mids.index, inplace=False
        )
        proposed_orders = target_position_values / fairs.mean - pair_positions
        prices = (proposed_orders >= 0) * asks + (proposed_orders < 0) * bids
        pct_edge = fairs.mean / prices - 1
        profitable = np.sign(proposed_orders) * pct_edge > fees + self.min_edge_to_enter
        trending_correctly = z_trend * np.sign(pct_edge) > self.trend_cutoff
        profitable_orders = proposed_orders * profitable * trending_correctly

        should_close = -np.sign(pair_positions) * pct_edge > fees + self.min_edge_to_close
        position_closing_orders = (
            -pair_positions * (1 - profitable) * should_close * trending_correctly
        )

        return profitable_orders + position_closing_orders
