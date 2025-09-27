import re
from typing import Optional, Dict

# Very lightweight heuristic extraction; can be replaced with LLM later.
DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")
TIME_PATTERN = re.compile(r"(\d{1,2}:[0-5]\d)")
PEOPLE_PATTERN = re.compile(r"(\d+) ?(명|사람|인원|people)")
LOCATION_PATTERN = re.compile(r"([가-힣A-Za-z]+)(?:지역|시|도|구|군)")
DEPARTURE_PATTERN = re.compile(r"(?:출발|집결)\s*(?:지|장)?\s*(?:은|는|:)?\s*([가-힣A-Za-z0-9\s]+)")

FIELD_ALIASES = {
    "date": ["날짜"],
    "time": ["시간"],
    "people": ["인원", "사람"],
    "location": ["지역", "장소"],
    "departure": ["출발", "집결"],
}

def extract_entities(message: str) -> Dict[str, Optional[str]]:
    data: Dict[str, Optional[str]] = {"date": None, "time": None, "people": None, "location": None, "departure": None}
    if m := DATE_PATTERN.search(message):
        data["date"] = m.group(1)
    if m := TIME_PATTERN.search(message):
        data["time"] = m.group(1)
    if m := PEOPLE_PATTERN.search(message):
        data["people"] = int(m.group(1))
    if m := LOCATION_PATTERN.search(message):
        data["location"] = m.group(1)
    if m := DEPARTURE_PATTERN.search(message):
        data["departure"] = m.group(1).strip()
    return data
