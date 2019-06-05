from collections import defaultdict
from queue import Queue
from threading import Lock

import numpy as np
import pandas as pd

from trader.util import Feed, Gaussian, Log
from trader.util.types import ExchangePair, TradingPair


class ExecutionStrategy:
    def __init__(self, size, min_edge, min_edge_to_close):
        self.size = size
        self.min_edge = min_edge
        self.min_edge_to_close = min_edge_to_close

    def tick(self, balances, bids, asks, fairs, fees):
        """Takes fair as Gaussian, balances in base currency.
        Returns orders in base currency (negative size indicates sell).

        Since our fair estimate may have skewed uncertainty, it may be the case that
        a price change for one trading pair causes us to desire positions in other
        pairs. Therefore get_orders needs to consider the entire set of fairs and
        bid/asks at once.

        TODO: generalize to multiple quotes
        TODO: use books instead of just the best bid/ask price
        """
        mids = (bids + asks) / 2  # Use mid price for target balance value calculations.

        gradient = fairs.gradient(mids) * fairs.mean
        balance_direction_vector = gradient / (np.linalg.norm(gradient) + 1e-100)
        target_balance_values = balance_direction_vector * fairs.z_score(mids) * self.size
        pair_balances = balances[[(ep.exchange_id, ep.base) for ep in mids.index]].set_axis(
            mids.index, inplace=False
        )
        proposed_orders = target_balance_values / fairs.mean - pair_balances
        prices = (proposed_orders >= 0) * asks + (proposed_orders < 0) * bids
        edge = fairs.mean / prices - 1
        profitable = np.sign(proposed_orders) * edge > fees + self.min_edge
        profitable_orders = proposed_orders * profitable

        should_close = -np.sign(pair_balances) * edge > fees + self.min_edge_to_close
        balance_closing_orders = -pair_balances * (1 - profitable) * should_close

        return profitable_orders + balance_closing_orders
