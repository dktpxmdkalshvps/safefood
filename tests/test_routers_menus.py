from fastapi.testclient import TestClient
from app.main import app
import pytest

client = TestClient(app)

def test_search_menus_avoid_allergies_length_limit():
    # Test valid request (30 items)
    valid_params = "&".join([f"avoid_allergies=allergy{i}" for i in range(30)])
    response = client.get(f"/api/v1/menus/search?{valid_params}")
    assert response.status_code == 200

    # Test invalid request (31 items, exceeds max_length of 30)
    invalid_params = "&".join([f"avoid_allergies=allergy{i}" for i in range(31)])
    response = client.get(f"/api/v1/menus/search?{invalid_params}")
    assert response.status_code == 422
    error_detail = response.json()["detail"][0]
    assert error_detail["type"] == "too_long"
    assert error_detail["loc"] == ["query", "avoid_allergies"]
