import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    import app as app_module
    return TestClient(app_module.app)


@pytest.fixture(scope="session")
def rocks(client):
    return client.get("/api/rocks", params={"fields": "full"}).json()["rocks"]
