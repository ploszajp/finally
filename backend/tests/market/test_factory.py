from app.market.cache import PriceCache
from app.market.factory import create_market_data_source
from app.market.interface import MarketDataSource
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource


def test_default_simulator(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    assert isinstance(create_market_data_source(PriceCache()), SimulatorDataSource)


def test_empty_and_whitespace_key_is_simulator(monkeypatch):
    for v in ("", "   "):
        monkeypatch.setenv("MASSIVE_API_KEY", v)
        assert isinstance(create_market_data_source(PriceCache()), SimulatorDataSource)


def test_key_selects_massive(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "abc")
    src = create_market_data_source(PriceCache())
    assert isinstance(src, MassiveDataSource)
    assert src._api_key == "abc"


def test_both_implement_interface():
    assert issubclass(SimulatorDataSource, MarketDataSource)
    assert issubclass(MassiveDataSource, MarketDataSource)


def test_interface_is_abstract():
    import pytest

    with pytest.raises(TypeError):
        MarketDataSource()  # type: ignore[abstract]
