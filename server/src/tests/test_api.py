import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import app

client = TestClient(app)

def test_chat_flow_missing_fields():
    r = client.post("/chat", json={"message": "안녕"})
    assert r.status_code == 200
    data = r.json()

    assert data["message"]
    assert isinstance(data["toolResults"], list)
    assert data["callSuggested"] is False

    planner_results = [
        result
        for result in data["toolResults"]
        if result.get("toolName") == "planner_agent"
    ]
    assert planner_results, "planner_agent tool result should be present"

    planner_metadata = planner_results[0].get("metadata", {})
    assert "missing" in planner_metadata
    assert len(planner_metadata["missing"]) > 0

def test_businesses_list():
    r = client.get("/businesses")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 0
