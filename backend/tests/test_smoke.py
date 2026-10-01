"""
Single smoke test for the NEXO pytest foundation.
"""
from sqlalchemy import create_engine, text

from tests.conftest import TEST_DATABASE_URL


def test_smoke(client, development_database_url):
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "OK"}

    home_response = client.get("/")
    assert home_response.status_code == 200
    home_payload = home_response.json()
    assert home_payload["company"] == "NEXO Technologies"
    assert home_payload["product"] == "NEXO Ride"

    assert "test" in TEST_DATABASE_URL.lower()

    test_engine = create_engine(TEST_DATABASE_URL)
    with test_engine.connect() as connection:
        test_database_name = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()
    test_engine.dispose()

    assert "test" in test_database_name.lower()

    if development_database_url:
        assert TEST_DATABASE_URL != development_database_url

        dev_engine = create_engine(development_database_url)
        with dev_engine.connect() as connection:
            development_database_name = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()
        dev_engine.dispose()

        assert test_database_name != development_database_name
