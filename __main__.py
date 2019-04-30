import pandas as pd

import trader.strategy as strategy
from trader.exchange import Bitfinex, DummyExchange
from trader.executor import Executor
from trader.metrics import Metrics
from trader.util.constants import (BTC_USD, BTC_USDT, ETH_USD, ETH_USDT,
                                   LTC_USDT, XRP_USDT, ExchangePair)
from trader.util.feed import Feed
from trader.util.log import Log
from trader.util.stats import Gaussian
from trader.util.thread import Beat, ThreadManager
from trader.util.types import Direction, Order

thread_manager = ThreadManager()
bitfinex = Bitfinex(thread_manager)
# If you don't have research/data/1min.h5, download 1min from S3 and run hd5.ipynb:
# data_min = pd.read_hdf("research/data/1min.h5")
# dummy_exchange = DummyExchange(thread_manager, data_min, {})

# dummy_strategy = strategy.Dummy()
# cointegrator_strategy = strategy.Cointegrator(
#     train_size=1200, validation_size=600, cointegration_period=64
# )
kalman_strategy = strategy.Kalman(512, 100, 32, 8)
executor = Executor(thread_manager, {bitfinex: [BTC_USD, ETH_USD]}, size=100, min_edge=0)
# executor = Executor(thread_manager, {dummy_exchange: [BTC_USDT, ETH_USDT]}, size=100, min_edge=0)
# metrics = Metrics(thread_manager, {bitfinex})


def main():
    beat = Beat(60000)
    while beat.loop():
        bitfinex_data = bitfinex.prices([BTC_USD, ETH_USD], "1m")
        kalman_fairs = kalman_strategy.tick(bitfinex_data)
        fairs = Gaussian.intersect([kalman_fairs])
        Log.info(fairs)
        if kalman_strategy.warmed_up:
            executor.tick_fairs(fairs)

# def dummy_main():
#     threads = 0
#     while True:
#         dummy_exchange.step_time()
#         dummy_data = dummy_exchange.prices([BTC_USDT, ETH_USDT], "1m")
#         # cointegration_fairs = cointegrator_strategy.step(dummy_data)
#         kalman_fairs = kalman_strategy.tick(dummy_data)
#         # executor.tick_fairs(cointegration_fairs)
#         executor.tick_fairs(kalman_fairs)


thread_manager.attach("main", main, should_terminate=True)
# thread_manager.attach("dummy_main", dummy_main, should_terminate=True)
thread_manager.run()
