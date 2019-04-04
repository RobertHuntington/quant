from trader.strategy.base import Strategy
from trader.util.stats import Gaussian


class Dummy(Strategy):
    """A strategy that always returns a null prediction."""

    def tick(self, frame):
        return self.null_estimate(frame)
