import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_chat_flow_missing_fields():
    r = client.post("/chat", json={"message": "안녕"})
    assert r.status_code == 200
    data = r.json()
    assert "missing" in data
    assert len(data["missing"]) > 0

def test_businesses_list():
    r = client.get("/businesses")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 0
