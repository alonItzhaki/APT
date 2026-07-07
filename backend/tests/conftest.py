import pytest

from apt.repo.db import connect, migrate


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    migrate(connection)
    yield connection
    connection.close()
