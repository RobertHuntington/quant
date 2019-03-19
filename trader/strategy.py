from abc import ABC, abstractmethod
from aiostream import pipe


class Strategy(ABC):
    def process(self, data_feed):
        return data_feed | pipe.map(self._tick)

    @abstractmethod
    def _tick(self, data):
        # `data` is a dictionary of { pair: ohlcv }.
        # Returns a dictionary of { pair: (fair_price, std_dev) }.
        pass
