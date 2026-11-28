import pytest

from app.db import init_db


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "sub" / "finally.db"


@pytest.fixture
def db(db_path):
    return init_db(db_path)
