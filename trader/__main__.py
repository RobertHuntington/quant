# TODO: Consider using threads if this gets out of hand.
from exchange import Exchange
from executor import Executor
from strategy import Strategy
from util import call_async, trace_exceptions

from concurrent.futures import ThreadPoolExecutor
from websocket import create_connection

import aiohttp
import asyncio
import json
import krakenex
import time


class Kraken(Exchange):
    # TODO: Get real Kraken account w/ KYC and money.
    def __init__(self):
        self.kraken = krakenex.API()
        # self.kraken.load_key('secret.key')

    async def _feed(self, pairs, time_interval):
        for _ in range(3):
            try:
                self.session = aiohttp.ClientSession()
                self.ws = await self.session.ws_connect('wss://ws-sandbox.kraken.com')
            except Exception as error:
                print('caught error: ' + repr(error))
                time.sleep(3)
            else:
                break
        await self.ws.send_str(json.dumps({
            'event': 'subscribe',
            'pair': pairs,
            'subscription': {
                'name': 'ohlc',
                'interval': time_interval
            }
        }))

        while True:
            try:
                result = await self.ws.receive()
                # TODO: Error handling of this await.
                result = json.loads(result.data)
                # Ignore heartbeats.
                if not isinstance(result, dict):
                    yield result
            except Exception as error:
                print('caught error: ' + repr(error))
                time.sleep(3)

    async def add_order(self, pair, side, order_type, price, volume):
        await call_async(lambda: self.kraken.query_private('AddOrder', {
            'pair': pair,
            'type': side,
            'ordertype': order_type,
            'price': price,
            'volume': volume
        }))

    async def cancel_order(self, order_id):
        await call_async(lambda: self.kraken.query_private('CancelOrder', {
            'txid': order_id
        }))

    async def get_balance(self):
        await call_async(lambda: self.kraken.query_private('Balance'))

    async def get_open_positions(self):
        await call_async(lambda: self.kraken.query_private('OpenPositions'))


class DummyExecutor(Executor):
    def __init__(self, exchange):
        super().__init__()
        self.exchange = exchange

    async def _tick(self, input):
        ((fair, stddev), data) = input
        close = float(data[1][5])
        print('Close: {}, Fair: {}, Stddev: {}'.format(close, fair, stddev))
        if close < fair - stddev:
            print('Buying 1 BTC at {}.'.format(close))
            # await self.exchange.add_order('XXBTZUSD', 'buy', 'market', close, 1)
        elif close > fair + stddev:
            print('Selling 1 BTC at {}.'.format(close))
            # await self.exchange.add_order('XXBTZUSD', 'sell', 'market', close, 1)


class DummyStrategy(Strategy):
    def _tick(self, data):
        # TODO: Strategy to derive fair estimate and stddev
        fair = float(data[1][5])
        stddev = 100.
        return ((fair, stddev), data)


async def main():
    exchange = Kraken()
    strategy = DummyStrategy()
    executor = DummyExecutor(exchange)
    exchange_feed = exchange.observe(['XBT/USD'], 5)
    strategy_feed = strategy.observe(exchange_feed)

    await asyncio.gather(
        trace_exceptions(executor.consume(strategy_feed)),
        trace_exceptions(executor.run())
    )

asyncio.run(main())
