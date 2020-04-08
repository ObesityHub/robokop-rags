from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_landing_page():
    response = client.get("/")
    assert response.status_code == 200

