import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine

import research.util.credentials as creds
from research.util.optimizer import BasicGridSearch, aggregate
from trader.exchange import DummyExchange
from trader.execution_strategy import ExecutionStrategy
from trader.executor import Executor
from trader.signal_aggregator import SignalAggregator
from trader.strategy import Kalman
from trader.util.constants import (BINANCE, BTC, BTC_USDT, EOS_USDT, ETH,
                                   ETH_USDT, LTC_USDT, NEO_USDT, XRP, XRP_USDT)
from trader.util.gaussian import Gaussian
from trader.util.thread import ThreadManager


def prepare_test_data(exchange_pairs, begin_time, end_time, tick_size_in_min):
    """
    Pulls test data from Postgres, in the form of a `DataFrame` of `DataFrame`s, for given exchanges
    and trading pairs, time interval, and tick size (over which by-the-minute trading data is
    aggregated by averaging prices and summing volumes). Fails for exchanges not present in DB,
    but silently ignores pairs with no trading data for corresponding exchange.

    prepare_test_data(
        {
            'binance': ['BTC/USDT', 'ETH/USDT'],
            'bitfinex': ['BTC/USD'],
        },
        '2017-08-18 08:00:00',
        '2017-08-20 09:00:00',
        5
    )
    returns a `DataFrame` of the form

    timestamp                                    pv
    2017-08-18 08:00:00+00:00                    pv_1
    2017-08-18 08:05:00+00:00                    pv_2
    2017-08-18 08:10:00+00:00                    pv_3
    ...

    where each `pv_i` is a `DataFrame` of the form

      timestamp                  pair              price     volume
    0 2017-08-18 08:00:00+00:00  binance-BTC-USDT  4291.100  2.605985
    1 2017-08-18 08:00:00+00:00  binance-ETH-USDT   307.494  8.248910
    2 2017-08-18 08:00:00+00:00  bitfinex-BTC-USD  4302.242  0.421329
    """
    pg_uri = "postgresql+psycopg2://{}:{}@{}:{}/{}".format(
        creds.PG_USERNAME,
        quote_plus(creds.PG_PASSWORD),
        creds.PG_HOST,
        creds.PG_PORT,
        creds.PG_DBNAME,
    )
    engine = create_engine(pg_uri)

    raw_test_data = pd.DataFrame()
    for exchange in exchange_pairs:
        pairs = [p.replace("/", "-") for p in exchange_pairs[exchange]]
        query = """
            SELECT
                TO_TIMESTAMP(
                    FLOOR(
                        EXTRACT(EPOCH FROM "timestamp") / (60 * {tick_size})
                    ) * 60 * {tick_size}
                ) AS tick_begin,
                pair,
                AVG("open")   AS price,
                SUM("volume") AS volume
            FROM {exchange}
            WHERE
                timestamp >= '{begin_time}' AND
                timestamp <= '{end_time}' AND
                pair IN ({pairs})
            GROUP BY tick_begin, pair
            HAVING COUNT(*) = {tick_size}
        """.format(
            exchange=exchange,
            tick_size=tick_size_in_min,
            begin_time=begin_time,
            end_time=end_time,
            pairs=", ".join(["'{}'".format(p) for p in pairs]),
        )

        raw_df = pd.read_sql(query, con=engine).rename({"tick_begin": "timestamp"}, axis=1)
        # Prepend name of exchange to trading pair
        raw_df["pair"] = exchange + "-" + raw_df["pair"]
        raw_test_data = pd.concat([raw_test_data, raw_df])

    # Transform DataFrame into df of dfs, indexed by timestamp
    test_data = pd.DataFrame(raw_test_data.groupby("timestamp"))
    test_data.columns = ["timestamp", "pv"]
    test_data.set_index("timestamp", inplace=True)
    return test_data


# td = prepare_test_data(
#     {"binance": ["BTC/USDT", "ETH/USDT", "dsfj/dgs"], "bitfinex": ["BTC/USD", "ETH/USD"]},
#     "2019-05-06 13:09:00",
#     "2019-05-06 13:16:00",
#     5,
# )
# print(td.head())
# print(td.iloc[0]["pv"])
# print(td.iloc[-1]["pv"])


def backtest_spark_job(input_path, sc):
    """
    Your entire job must go within the function definition (including imports).

    TODO: integrate with prepare_test_data to pull from DB instead of HDF from disk
    """
    def inside_job(strategy, executor, **kwargs):
        data = pd.read_hdf(input_path).resample("15Min").first()
        window_size = 50
        warmup_data = data.iloc[:window_size]
        data = data.iloc[window_size : window_size * 2]
        thread_manager = ThreadManager()
        dummy_exchange = DummyExchange(
            thread_manager, BINANCE, data, {"maker": 0.00075, "taker": 0.00075}
        )
        pairs = [BTC_USDT, ETH_USDT, XRP_USDT, LTC_USDT, NEO_USDT, EOS_USDT]
        execution_strategy = ExecutionStrategy(10, 192, 1, 3, -0.5, 0.002, 0.0005, warmup_data)
        executor = executor(thread_manager, {dummy_exchange: pairs}, execution_strategy)
        aggregator = SignalAggregator(window_size, {"total_market": [p.base for p in pairs]})
        warmup_signals = warmup_data.apply(aggregator.step, axis=1)
        strat = strategy(**kwargs, warmup_signals=warmup_signals, warmup_data=warmup_data)

        fair_history = []
        position_history = []

        def main():
            for row in data.iterrows():
                if not dummy_exchange.step_time():
                    break
                dummy_data = dummy_exchange.frame(pairs)
                signals = aggregator.step(dummy_data)
                kalman_fairs = strat.tick(dummy_data, signals)
                fairs = kalman_fairs & Gaussian(
                    dummy_data.xs("price", level=1),
                    [1e100 for _ in dummy_data.xs("price", level=1).index],
                )
                executor.tick_fairs(fairs)
                fair_history.append(fairs)
                position_history.append(dummy_exchange.positions.copy())

        thread_manager.attach("main", main, should_terminate=True)
        thread_manager.run()
        return {
            "data": data,
            "fairs": pd.DataFrame(fair_history, index=data.index),
            # Should be called 'positions' but analysis.py must also change
            "balances": pd.DataFrame(position_history, index=data.index),
        }

    param_spaces = {
        "strategy": [Kalman],
        "executor": [Executor],
        "window_size": range(500, 501, 1),
        "movement_hl": range(6, 7, 1),
        "trend_hl": range(256, 257, 1),
        "mse_hl": range(192, 193, 1),
        "cointegration_period": range(32, 33, 1),
        "maxlag": range(8, 9, 1),
    }
    return aggregate(sc, inside_job, param_spaces, parallelism=2)


def backtest():
    # NOTE: Keep me at the top. (Sets up the module environment to run this script.)
    import scripts.setup  # isort:skip, pylint: disable=import-error

    import os
    import sys
    from importlib.machinery import SourceFileLoader

    from pyspark import SparkContext

    # Assumes you have JDK 1.8 as installed in the setup script.
    os.environ["PYSPARK_PYTHON"] = "python3"
    os.environ["JAVA_HOME"] = "/Library/Java/JavaVirtualMachines/adoptopenjdk-8.jdk/Contents/Home"

    job = backtest_spark_job

    # Run the job locally.
    sc = SparkContext("local", "backtest")
    value = job("research/data/1min.h5", sc)
    sc.stop()

    return value


def analyze_spark_job(sc, results):
    """
    Your entire job must go within the function definition (including imports).
    """

    def principal_market_movements(prices):
        """Returns principal vectors for 1-stddev market movements, plus explained variance ratios"""
        # Fit PCA to scaled (mean 0, variance 1) matrix of single-tick price differences
        pca = PCA(n_components=0.97)
        RISK_WINDOW = 10
        scaler = StandardScaler()
        price_deltas = prices.diff().iloc[1:].rolling(RISK_WINDOW).sum().iloc[RISK_WINDOW:]
        price_deltas_scaled = scaler.fit_transform(price_deltas)
        pca.fit(price_deltas_scaled)
        pcs = pd.DataFrame(scaler.inverse_transform(pca.components_), columns=price_deltas.columns)
        return (pcs, pca.explained_variance_ratio_)

    def max_abs_drawdown(pnls):
        """Maximum peak-to-trough distance before a new peak is attained. The usual metric, expressed
        as a fraction of peak value, does not make sense in the infinite-leverage context."""
        max_drawdown = 0
        peak = -np.inf
        for pnl in pnls:
            if pnl > peak:
                peak = pnl
            drawdown = peak - pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        return max_drawdown

    def inside_job():
        import numpy as np

        """Analyzes P/L and various risk metrics for the given run results.

        Note: RoRs are per-tick. They are NOT comparable across time scales."""
        # Balance values
        price_data = results["data"].xs("price", axis=1, level=1)
        quote_currency = price_data.columns[0].quote
        prices_ = price_data.rename(columns=lambda pair: pair.base)
        prices_[quote_currency] = 1
        balance_values = results["balances"] * prices_

        pnls = balance_values.sum(axis=1)
        pnl = pnls.iloc[-1]

        # Market risk
        (pmms, pmm_weights) = principal_market_movements(price_data)
        for row in price_data.columns:
            if row not in results["balances"]:
                results["balances"][row] = 0.0

        balances_ = results["balances"][[pair.base for pair in price_data.columns]].set_axis(
            price_data.columns, axis=1, inplace=False
        )
        component_risks = np.abs(balances_ @ pmms.T)
        risks = component_risks @ pmm_weights

        total_positions = np.abs(balance_values.drop(columns=[quote_currency]).values).sum()
        max_drawdown = max_abs_drawdown(pnls)

        return {
            "balances_usd": results["balances"].iloc[-1],
            "pnl": pnl,
            "max_market_risk": risks.values.max(),
            "max_drawdown": max_drawdown,
            "return_on_max_market_risk": pnl / (risks.values.max() + 1e-10),
            "return_on_max_drawdown": pnl / (max_drawdown + 1e-10),
            "return_on_total_position": pnl / (total_positions + 1e-10),
            "sharpe_ratio": pnl / (pnls.std() + 1e-10),
        }

    param_spaces = {}
    return aggregate(sc, inside_job, param_spaces, parallelism=2)


def analyze(results):
    # NOTE: Keep me at the top. (Sets up the module environment to run this script.)
    import scripts.setup  # isort:skip, pylint: disable=import-error

    import os
    import sys
    from importlib.machinery import SourceFileLoader

    from pyspark import SparkContext

    # Assumes you have JDK 1.8 as installed in the setup script.
    os.environ["PYSPARK_PYTHON"] = "python3"
    os.environ["JAVA_HOME"] = "/Library/Java/JavaVirtualMachines/adoptopenjdk-8.jdk/Contents/Home"

    job = analyze_spark_job

    # Run the job locally.
    sc = SparkContext("local", "backtest")
    value = job(sc, results)
    sc.stop()

    return value
