import pytest

from app.market import InvalidTickerError, PriceCache, normalize_ticker
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource
from app.market.tickers import normalize_tickers

INVALID = ["", "   ", "not a ticker!!", "ABCDEFGHIJK", "1ABC", ".A", "AA/BB", "AAPL\nMSFT"]


@pytest.mark.parametrize(
    "raw,expected", [(" aapl ", "AAPL"), ("brk.b", "BRK.B"), ("BF-B", "BF-B"), ("v", "V")]
)
def test_normalize(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", INVALID)
def test_invalid(raw):
    with pytest.raises(InvalidTickerError):
        normalize_ticker(raw)


def test_startup_list_dedupes_and_skips_invalid():
    assert normalize_tickers(["aapl", "", "AAPL", "bad ticker", "v"]) == ["AAPL", "V"]


@pytest.mark.parametrize("method", ["add_ticker", "remove_ticker"])
@pytest.mark.parametrize("make_source", [SimulatorDataSource, lambda c: MassiveDataSource("k", c)])
async def test_both_sources_reject_invalid(make_source, method):
    source = make_source(PriceCache())
    with pytest.raises(InvalidTickerError):
        await getattr(source, method)("not a ticker!!")
    assert source.get_tickers() == []
