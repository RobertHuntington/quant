"""The `constants` module.

Constants to identify common entities in the code.

"""

from trader.util.types import Currency, TradingPair

# Exchanges.
BITFINEX = "bitfinex"
DUMMY = "dummy"
KRAKEN = "kraken"


# Currencies.
USD = Currency("USD")
USDT = Currency("USDT")
BTC = Currency("BTC")
ETH = Currency("ETH")
XRP = Currency("XRP")
LTC = Currency("LTC")
EOS = Currency("EOS")
NEO = Currency("NEO")
STABLECOINS = {USD, USDT}


# USD quotes.
BTC_USD = TradingPair(BTC, USD)
ETH_USD = TradingPair(ETH, USD)
XRP_USD = TradingPair(XRP, USD)
LTC_USD = TradingPair(LTC, USD)
EOS_USD = TradingPair(EOS, USD)
NEO_USD = TradingPair(NEO, USD)

# USDT quotes.
BTC_USDT = TradingPair(BTC, USDT)
ETH_USDT = TradingPair(ETH, USDT)
XRP_USDT = TradingPair(XRP, USDT)
NEO_USDT = TradingPair(NEO, USDT)
LTC_USDT = TradingPair(LTC, USDT)
EOS_USDT = TradingPair(EOS, USDT)


def not_implemented():
    raise NotImplementedError("not implemented")
