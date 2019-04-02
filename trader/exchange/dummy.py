import hashlib
import hmac
import json
import os
import random
import time
from collections import defaultdict
from queue import Queue

import pandas as pd
from bitfinex import ClientV1, ClientV2, WssClient
from sortedcontainers import SortedList
from websocket import create_connection

from trader.exchange.base import Exchange, ExchangeError
from trader.util.constants import (BTC, BTC_USDT, ETH, ETH_USDT, USD, XRP,
                                   XRP_USDT, not_implemented)
from trader.util.feed import Feed
from trader.util.log import Log
from trader.util.types import Direction, Order, OrderBook


class DummyExchange(Exchange):
    """Dummy exchange. Uses historical data and executes orders at last trade price.
    """

    # Allow only 1 instance. In the near future we should change the exchange classes to actually
    # be singletons, but first we should extract common logic into the Exchange base class before
    # making that change.
    __instance_exists = False

    def __init__(self, thread_manager, data, fees):
        assert not DummyExchange.__instance_exists
        DummyExchange.__instance_exists = True
        super().__init__(thread_manager)
        self.__data = data
        self.__supported_pairs = data.iloc[0].index
        # time is not private to allow manual adjustment.
        self.time = 0
        self.__fees = {"maker": 0.001, "taker": 0.002}
        self.__book_queues = {pair: Queue() for pair in self.__supported_pairs}
        self.__books = {}
        self.__prices = {pair: (0, 0) for pair in self.__supported_pairs}
        self.__balances = defaultdict(float)
        self.translate = {BTC_USDT: "BTC_USDT", ETH_USDT: "ETH_USDT", XRP_USDT: "XRP_USDT"}
        self.__order_id = 0

    @property
    def id(self):
        return "DUMMY_EXCHANGE"

    def step_time(self):
        data = self.__data.iloc[self.time]
        data_list = list(data.items())
        prices = list(data_list[0][1].items())
        volumes = list(data_list[1][1].items())
        pair_data = list(map(lambda x: (x[0][1], x[1][1]), list(zip(prices, volumes))))
        for i, pair in enumerate(self.__supported_pairs):
            self.__book_queues[pair].put(pair_data[i])
            self.__prices[pair] = pair_data[i]
        Log.info("Dummy step {} prices {}".format(self.time, self.__prices))
        self.time += 1

    def book(self, pair):
        pair = self.translate[pair]
        if pair not in self.__supported_pairs:
            raise ExchangeError("pair not supported by " + self.id)
        if pair in self.__books:
            return self.__books[pair]
        else:
            pair_feed, runner = Feed.of(self.__book(pair))
            self._thread_manager.attach("dummy-{}-book".format(pair), runner)
            self.__books[pair] = pair_feed
            return pair_feed

    def __book(self, pair):
        while True:
            (price, volume) = self.__book_queues[pair].get()
            spread = random.random()
            yield OrderBook(self, pair, price, price - spread, price + spread)

    def prices(self, pairs, time_frame=None):
        """

        NOTE: `time_frame` expected as Bitfinex-specific string representation (e.g. '1m').

        """
        data = {"close": [], "volume": []}
        for pair in pairs:
            pair = self.translate[pair]
            if pair not in self.__supported_pairs:
                raise ExchangeError("pair not supported by Bitfinex")
            if pair in self.__prices:
                val = self.__prices[pair]
            else:
                # Prices should be tracked in `step_time`
                val = (0, 0)
            data["close"].append(val[0])
            data["volume"].append(val[1])
        return pd.DataFrame.from_dict(data, orient="index", columns=pairs)

    @property
    def balances(self):
        return self.__balances

    @property
    def fees(self):
        return self.__fees

    def add_order(self, pair, side, order_type, price, volume, maker=False):
        if side == Direction.BUY:
            Log.info("Buying {} {} at price {} {}".format(volume, pair.base(), price, pair.quote()))
            self.__balances[pair.base()] += volume
            self.__balances[pair.quote()] -= volume * price
        else:
            Log.info(
                "Selling {} {} at price {} {}".format(volume, pair.base(), price, pair.quote())
            )
            self.__balances[pair.base()] -= volume
            self.__balances[pair.quote()] += volume * price
        order = Order(self.__order_id, self.id, pair, side, order_type, price, volume)
        self.__order_id += 1
        Log.info("Balance: {}".format(self.__balances))
        return order

    # Unnecessary since orders are immediate
    def cancel_order(self, order_id):
        not_implemented()

    # Unnecessary since orders are immediate
    def get_open_positions(self):
        not_implemented()
