import os
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from app.market.seed_prices import SEED_PRICES
from app.market.simulator import GBMSimulator, seed_price


def test_step_returns_all_tickers():
    sim = GBMSimulator(["AAPL", "GOOGL"])
    assert set(sim.step()) == {"AAPL", "GOOGL"}


def test_prices_positive():
    sim = GBMSimulator(["AAPL"], event_probability=0.01)
    for _ in range(5000):
        assert sim.step()["AAPL"] > 0


def test_initial_prices_match_seeds():
    sim = GBMSimulator(["AAPL"])
    assert sim.get_price("AAPL") == SEED_PRICES["AAPL"]


def test_add_remove():
    sim = GBMSimulator(["AAPL"])
    sim.add_ticker("TSLA")
    assert "TSLA" in sim.step()
    sim.remove_ticker("TSLA")
    assert "TSLA" not in sim.step()
    assert sim.get_tickers() == ["AAPL"]


def test_duplicate_and_missing_are_noops():
    sim = GBMSimulator(["AAPL"])
    sim.add_ticker("AAPL")
    sim.remove_ticker("NOPE")
    assert sim.get_tickers() == ["AAPL"]


def test_unknown_ticker_random_price():
    p = GBMSimulator(["ZZZZ"]).get_price("ZZZZ")
    assert 50.0 <= p <= 300.0


def test_empty_step():
    assert GBMSimulator([]).step() == {}


def test_cholesky_lifecycle():
    sim = GBMSimulator(["AAPL"])
    assert sim._cholesky is None
    sim.add_ticker("GOOGL")
    assert sim._cholesky is not None
    sim.remove_ticker("GOOGL")
    assert sim._cholesky is None


def test_all_default_tickers():
    sim = GBMSimulator(list(SEED_PRICES))
    assert sim._cholesky is not None and sim._cholesky.shape == (10, 10)
    assert set(sim.step()) == set(SEED_PRICES)


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("AAPL", "MSFT", 0.6),
        ("JPM", "V", 0.5),
        ("AAPL", "JPM", 0.3),
        ("TSLA", "AAPL", 0.3),
        ("ZZZZ", "AAPL", 0.3),
    ],
)
def test_pairwise_correlation(a, b, expected):
    assert GBMSimulator._pairwise_correlation(a, b) == expected
    assert GBMSimulator._pairwise_correlation(b, a) == expected


def test_gbm_math_deterministic():
    """With no shocks, one step equals S*exp(drift + sigma*sqrt(dt)*Z)."""
    np.random.seed(1)
    expected_z = np.random.standard_normal(1)[0]
    np.random.seed(1)
    sim = GBMSimulator(["AAPL"], event_probability=0.0)
    mu, sigma, dt = 0.05, 0.22, sim._dt
    import math

    expected = 190.0 * math.exp((mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * expected_z)
    assert sim.step()["AAPL"] == round(expected, 2)


def test_log_return_volatility_matches_sigma():
    np.random.seed(7)
    # Large dt so per-step moves are visible after 2-decimal rounding.
    sim = GBMSimulator(["AAPL"], dt=1e-4, event_probability=0.0)
    rets = []
    for _ in range(4000):
        p = sim._prices["AAPL"]
        sim.step()
        rets.append(np.log(sim._prices["AAPL"] / p))
    est = np.std(rets) / np.sqrt(1e-4)
    assert est == pytest.approx(0.22, rel=0.1)


def test_correlated_moves():
    np.random.seed(3)
    sim = GBMSimulator(["AAPL", "MSFT"], dt=1e-4, event_probability=0.0)
    ra, rb = [], []
    for _ in range(4000):
        a, b = sim._prices["AAPL"], sim._prices["MSFT"]
        sim.step()
        ra.append(np.log(sim._prices["AAPL"] / a))
        rb.append(np.log(sim._prices["MSFT"] / b))
    assert np.corrcoef(ra, rb)[0, 1] == pytest.approx(0.6, abs=0.08)


def test_events_fire_with_probability_one():
    random.seed(0)
    sim = GBMSimulator(["AAPL"], event_probability=1.0)
    before = sim.get_price("AAPL")
    sim.step()
    ratio = sim._prices["AAPL"] / before
    assert 0.019 <= abs(ratio - 1) <= 0.051


def test_params_not_shared_between_instances():
    a = GBMSimulator(["ZZZZ"])
    a._params["ZZZZ"]["sigma"] = 9
    assert GBMSimulator(["YYYY"])._params["YYYY"]["sigma"] == 0.25


def test_unknown_ticker_price_survives_re_add():
    sim = GBMSimulator(["PYPL"])
    first = sim.get_price("PYPL")
    sim.remove_ticker("PYPL")
    sim.add_ticker("PYPL")
    assert sim.get_price("PYPL") == first


def test_seed_price_is_stable_across_processes():
    """A different hash seed per process must not change the result."""
    code = "from app.market.simulator import seed_price; print(seed_price('PYPL'))"
    for hash_seed in ("1", "2"):
        out = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
            capture_output=True,
            text=True,
            check=True,
        )
        assert float(out.stdout) == seed_price("PYPL")
