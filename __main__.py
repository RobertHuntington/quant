import trader.executor as executor
import trader.strategy as strategy
from trader.exchange import Exchanges
from trader.util.constants import BITFINEX, BTC_USD
from trader.util.stats import Gaussian
from trader.util.thread import Beat, ThreadManager

bitfinex = Exchanges.get(BITFINEX)
dummy_strategy = strategy.Dummy()
dummy_executor = executor.Dummy()


def main():
    beat = Beat(60000)
    while beat.loop():
        bitfinex_data = bitfinex.prices([BTC_USD], '1m')
        dummy_fairs = dummy_strategy.tick(bitfinex_data)
        fairs = Gaussian.intersect([dummy_fairs])
        dummy_executor.tick(fairs)


book_feed = bitfinex.book(BTC_USD)
executor_feed_runner = book_feed.subscribe(dummy_executor.main)

thread_manager = ThreadManager()
thread_manager.attach('main', main)
thread_manager.attach('book_feed', book_feed.run)
thread_manager.attach('executor', executor_feed_runner)
thread_manager.run()
