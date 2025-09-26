import re
from typing import Optional, Dict

# Very lightweight heuristic extraction; can be replaced with LLM later.
DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")
TIME_PATTERN = re.compile(r"(\d{1,2}:[0-5]\d)")
PEOPLE_PATTERN = re.compile(r"(\d+) ?(명|사람|인원|people)")
PHONE_PATTERN = re.compile(r"(01[016789]\d{7,8})")
LOCATION_PATTERN = re.compile(r"([가-힣A-Za-z]+)(?:지역|시|도|구|군)")

FIELD_ALIASES = {
    "date": ["날짜"],
    "time": ["시간"],
    "people": ["인원", "사람"],
    "location": ["지역", "장소"],
    "phone_user": ["전화", "번호"],
}

def extract_entities(message: str) -> Dict[str, Optional[str]]:
    data: Dict[str, Optional[str]] = {"date": None, "time": None, "people": None, "location": None, "phone_user": None}
    if m := DATE_PATTERN.search(message):
        data["date"] = m.group(1)
    if m := TIME_PATTERN.search(message):
        data["time"] = m.group(1)
    if m := PEOPLE_PATTERN.search(message):
        data["people"] = int(m.group(1))
    if m := PHONE_PATTERN.search(message):
        data["phone_user"] = m.group(1)
    if m := LOCATION_PATTERN.search(message):
        data["location"] = m.group(1)
    return data
