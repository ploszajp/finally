import threading

from app.market.cache import PriceCache


def test_update_and_get():
    c = PriceCache()
    u = c.update("AAPL", 190.5)
    assert c.get("AAPL") == u
    assert c.get_price("AAPL") == 190.5
    assert c.get_price("NOPE") is None
    assert c.get("NOPE") is None


def test_first_update_flat():
    u = PriceCache().update("AAPL", 190.5)
    assert u.direction == "flat" and u.previous_price == 190.5


def test_directions():
    c = PriceCache()
    c.update("AAPL", 190.0)
    assert c.update("AAPL", 191.0).direction == "up"
    assert c.update("AAPL", 190.0).direction == "down"


def test_rounding():
    assert PriceCache().update("A", 10.456).price == 10.46


def test_explicit_timestamp_including_zero():
    c = PriceCache()
    assert c.update("A", 1.0, timestamp=123.0).timestamp == 123.0
    assert c.update("A", 1.0, timestamp=0.0).timestamp == 0.0


def test_remove_and_contains_and_len():
    c = PriceCache()
    c.update("A", 1.0)
    c.update("B", 2.0)
    assert "A" in c and len(c) == 2
    c.remove("A")
    assert "A" not in c and len(c) == 1
    c.remove("A")  # no-op


def test_get_all_is_copy():
    c = PriceCache()
    c.update("A", 1.0)
    snap = c.get_all()
    snap.pop("A")
    assert "A" in c


def test_version():
    c = PriceCache()
    v = c.version
    c.update("A", 1.0)
    assert c.version == v + 1
    c.remove("A")
    assert c.version == v + 2
    c.remove("A")  # nothing removed, no bump
    assert c.version == v + 2


def test_thread_safety():
    c = PriceCache()

    def work(name):
        for i in range(500):
            c.update(name, 100.0 + i)

    threads = [threading.Thread(target=work, args=(f"T{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(c) == 8
    assert c.version == 8 * 500
