import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import app
from agent.planner import planner_agent

client = TestClient(app)

def test_chat_flow_missing_fields():
    mock_payload = {
        "plan_updates": {},
        "missing_information": [
            "date",
            "participants",
            "departure",
            "fishing_type",
            "budget",
            "gear",
            "transportation",
        ],
        "summary": ["새로운 계획 정보가 감지되지 않았습니다."],
    }

    with planner_agent.mock_response(mock_payload):
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
    assert isinstance(planner_metadata["missing"], list)
    assert len(planner_metadata["missing"]) == 0

    plan_payload = planner_metadata.get("plan", {})
    assert plan_payload.get("location") == "구룡포"
    assert plan_payload.get("participants") == 2
    assert plan_payload.get("departure") == "포항역 집결 04:00 출발"
    assert plan_payload.get("time") == "새벽 5시 ~ 오전 11시"

def test_businesses_list():
    r = client.get("/businesses")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 0
