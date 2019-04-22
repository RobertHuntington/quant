"""Spark/EMR optimizer tools."""

import os
from abc import ABC, abstractmethod
from itertools import islice, product


def _dict_product(d):
    """Maps `{a: [x, y], b: [z, w]}`
         to `[{a: x, b: z}, {a: x, b: w}, {a: y, b: z}, {a: y, b: w}]`.

    """
    return (dict(zip(d.keys(), vs)) for vs in product(*d.values()))


def _take(n, iterable):
    """Takes the first `n` items of the given iterable."""
    return list(islice(iterable, n))


class Optimizer(ABC):
    """An abstract class for param search optimizers.

    Args:
        param_spaces (Dict): A dictionary from named parameters to the values they can take on. Each
            optimizer can choose to support discrete or continuous parameters as desired.

    """

    @abstractmethod
    def __init__(self, param_spaces):
        pass

    @abstractmethod
    def next_trials(self, last_results=None):
        """Given some feedback `last_results` from the last set of trials, output the next set of
        parameter trials.

        Args:
            last_results (Comparable): Results of the last set of trials from this function. Use
                `None` if calling this for the first time.

        Returns:
            list: A list of dicts from named parameters to trial values.

        """
        pass

    @abstractmethod
    def best_params(self):
        """Return a tuple of (best params, best result) so far (`None` if no trials have run)."""
        pass


class BasicGridSearch(Optimizer):
    def __init__(self, param_spaces, chunk_size=None):
        """Expects `param_spaces` to contain generator expressions for grid values."""
        self.__trials = _dict_product(param_spaces)
        self.__chunk_size = chunk_size
        self.__last_trials = None
        self.__best_params = None
        self.__best_result = None
        self.__done = False

    def next_trials(self, last_results=None):
        # Update the best parameters based on results.
        # Other optimizers might use this to adapt their search.
        if last_results is not None and self.__last_trials is not None:
            for i in range(len(last_results)):
                params = self.__last_trials[i]
                result = last_results[i]

                if self.__best_result is None or result > self.__best_result:
                    self.__best_params = params
                    self.__best_result = result

        if self.__done:
            # Set this to None after results are fed back for the last time.
            self.__last_params = None
            return None

        # Return all trials at once?
        if self.__chunk_size is None:
            trials = list(self.__trials)
            self.__done = True
        # Or chunk?
        else:
            trials = _take(self.__chunk_size, self.__trials)
            if len(trials) < self.__chunk_size:
                self.__done = True

        self.__last_trials = trials
        return trials

    def best_params(self):
        return (self.__best_params, self.__best_result)


def _optimize(sc, strategy, runner, param_spaces, parallelism):
    def sim(kwargs):
        return runner(**kwargs)

    optimizer = strategy(param_spaces)
    last_results = None
    while True:
        trials = optimizer.next_trials(last_results)
        if trials is None:
            break
        rdd = sc.parallelize(trials, parallelism)
        last_results = rdd.map(sim).collect()
    return optimizer.best_params()


def optimize_local(name, strategy, runner, param_spaces):
    # Assumes you have JDK 1.8 as installed in the setup script.
    os.environ["PYSPARK_PYTHON"] = "python3"
    os.environ["JAVA_HOME"] = "/Library/Java/JavaVirtualMachines/adoptopenjdk-8.jdk/Contents/Home"

    # This import is often stateful.
    from pyspark import SparkContext

    sc = SparkContext("local", name)
    return _optimize(sc, strategy, runner, param_spaces, 1)


def optimize_emr(name, strategy, runner, param_spaces, parallelism):
    # This import is often stateful.
    from pyspark import SparkContext

    sc = SparkContext.getOrCreate()
    # TODO: Write result out to S3 and print it to console in shell script.
    return _optimize(sc, strategy, runner, param_spaces, parallelism)


def test_optimize_local():
    # Vertex at (3, -2, 3).
    def paraboloid(a, b):
        return -1 * ((a - 3) ** 2 + (b + 2) ** 2) + 3

    param_spaces = {"a": range(-10, 10, 1), "b": range(-5, 5, 1)}
    assert optimize_local("paraboloid", BasicGridSearch, paraboloid, param_spaces) == (
        {"a": 3, "b": -2},
        3,
    )
