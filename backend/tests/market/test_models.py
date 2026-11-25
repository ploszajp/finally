from app.market.models import PriceUpdate


def test_up():
    u = PriceUpdate("AAPL", 191.0, 190.0, 1.0)
    assert u.direction == "up"
    assert u.change == 1.0
    assert u.change_percent == round(1 / 190 * 100, 4)


def test_down():
    u = PriceUpdate("AAPL", 189.0, 190.0, 1.0)
    assert u.direction == "down"
    assert u.change == -1.0


def test_flat():
    u = PriceUpdate("AAPL", 190.0, 190.0, 1.0)
    assert u.direction == "flat"
    assert u.change == 0
    assert u.change_percent == 0


def test_zero_previous():
    assert PriceUpdate("X", 5.0, 0.0, 1.0).change_percent == 0.0


def test_to_dict():
    d = PriceUpdate("AAPL", 191.0, 190.0, 12.5).to_dict()
    assert set(d) == {
        "ticker", "price", "previous_price", "timestamp",
        "change", "change_percent", "direction",
    }
    assert d["timestamp"] == 12.5
    assert d["direction"] == "up"


def test_frozen():
    import dataclasses

    import pytest

    u = PriceUpdate("A", 1.0, 1.0, 1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        u.price = 2.0  # type: ignore[misc]
