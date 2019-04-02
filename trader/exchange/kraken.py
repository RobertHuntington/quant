from collections import defaultdict

import krakenex
import pandas as pd

from trader.exchange.base import Exchange
from trader.util.constants import BTC_USD, ETH_USD, KRAKEN, XRP_USD, not_implemented


class Kraken(Exchange):
    """The Kraken exchange.

    TODO: Complete this stub.

    """

    # Allow only 1 instance. In the near future we should change the exchange classes to actually
    # be singletons, but first we should extract common logic into the `Exchange` base class before
    # making that change.
    __instance_exists = False

    def __init__(self, thread_manager):
        assert not Kraken.__instance_exists
        Kraken.__instance_exists = True
        not_implemented()
        super().__init__(thread_manager)
        self.__kraken = krakenex.API()
        # self.__kraken.load_key('secret.key')
        self.__translate = {BTC_USD: "XXBTZUSD", ETH_USD: "XETHZUSD", XRP_USD: "XXRPZUSD"}
        self.__fees = {"maker": 0.0016, "taker": 0.0026}
        self.__balances = defaultdict(float)

    @property
    def id(self):
        return KRAKEN

    # TODO
    def book(self, pair):
        pass

    # TODO
    def prices(self, pairs, time_frame):
        """

        NOTE: `time_frame` expected to be integer in minutes (Kraken-specific).

        """
        data = {"close": [], "volume": []}
        for pair in pairs:
            pair = self.__translate[pair]
            params = {"pair": pair, "timeframe": time_frame}
            # Most recent update is second to last element in array (last element is an ongoing
            # candle).
            # Fields: open, high, low, close, vwap, volume
            ohlcvv = self.__kraken.query_public("OHLC", data=params)["result"][pair][-2][1:]
            data["close"].append(ohlcvv[3])
            data["volume"].append(ohlcvv[5])
        return pd.DataFrame.from_dict(data, orient="index", columns=pairs)

    # TODO
    @property
    def balances(self):
        return self.__balances

    # TODO
    @property
    def fees(self):
        # TODO: Update fees by pair schedule.
        return self.__fees

    def add_order(self, pair, side, order_type, price, volume, maker=False):
        pair = self.__translate[pair]
        query = {
            "pair": pair,
            "type": side,
            "ordertype": order_type,
            "price": price,
            "volume": volume,
        }
        if maker:
            query["oflags"] = "post"
        self.__kraken.query_private("AddOrder", query)

    def cancel_order(self, order_id):
        self.__kraken.query_private("CancelOrder", {"txid": order_id})

    def get_balance(self):
        self.__kraken.query_private("Balance")

    def get_open_positions(self):
        self.__kraken.query_private("OpenPositions")
