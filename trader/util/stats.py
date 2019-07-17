"""The `stats` module.

Helpful statistical models and indicators.

Note: In literature on moving averages, you'll see "value" referred to as "level".

"""

import numpy as np


class Ema:
    """
    Exponentially-weighted moving average.
    """

    def __init__(self, half_life, value_0=None):
        self.__a = 0.5 ** (1 / half_life)
        if value_0 is None:
            self.__value = None
            self.__samples_needed = half_life
        else:
            self.__value = value_0
            self.__samples_needed = 0

    @property
    def a(self):
        return self.__a

    @property
    def value(self):
        return self.__value

    def step(self, x):
        if self.__value is None:
            self.__value = x
        self.__value = self.__a * self.__value + (1 - self.__a) * x
        self.__samples_needed = max(0, self.__samples_needed - 1)
        return self.__value

    @property
    def ready(self):
        return self.__samples_needed == 0


class Emse:
    """
    Exponentially-weighted moving mean squared-erroer.
    """

    def __init__(self, half_life, mse_0=None):
        self.__a = 0.5 ** (1 / half_life)
        if mse_0 is None:
            self.__mse = 0
            self.__samples_needed = half_life
        else:
            self.__mse = mse_0
            self.__samples_needed = 0

    @property
    def mse(self):
        return self.__mse

    @property
    def stderr(self):
        return np.sqrt(self.__mse)

    def step(self, e):
        self.__mse = self.__a * (self.__mse + (1 - self.__a) * e ** 2)
        self.__samples_needed = max(0, self.__samples_needed - 1)
        return self.__mse

    @property
    def ready(self):
        return self.__samples_needed == 0


class HoltEma:
    """
    Holt's linear exponential smoothing, with optional moving mean squared-error.

    Implementation from https://people.duke.edu/~rnau/411avg.htm
    """

    def __init__(self, value_half_life, trend_half_life, mse_half_life=None):
        self.__a = 0.5 ** (1 / value_half_life)
        self.__b = 0.5 ** (1 / trend_half_life)
        self.__c = 0.5 ** (1 / mse_half_life) if not mse_half_life is None else None
        self.__value = None
        self.__trend = 0
        self.__mse = 0 if not mse_half_life is None else None
        self.__samples_needed = max(value_half_life, trend_half_life)

    @property
    def value(self):
        return self.__value

    @property
    def trend(self):
        return self.__trend

    @property
    def mse(self):
        return self.__mse

    @property
    def stderr(self):
        return np.sqrt(self.__mse)

    def step(self, x):
        if self.__value is None:
            self.__value = x
        value_old = self.__value
        self.__value = self.__a * (self.__value + self.__trend) + (1 - self.__a) * x
        self.__trend = self.__b * self.__trend + (1 - self.__b) * (self.__value - value_old)
        if not self.__mse is None:
            err = x - (self.__value + self.__trend)
            self.__mse = self.__c * (self.__mse + (1 - self.__c) * err ** 2)
        self.__samples_needed = max(0, self.__samples_needed - 1)
        return self.__value

    @property
    def ready(self):
        return self.__samples_needed == 0


class TrendEstimator:
    def __init__(self, estimator, init=None):
        self.estimator = estimator
        self.__prev = init

    @property
    def prev(self):
        return self.__prev

    @property
    def ready(self):
        return self.estimator.ready

    def step(self, x):
        if self.__prev is None:
            self.__prev = x
        diff = x - self.__prev
        self.__prev = x
        return self.estimator.step(diff)
