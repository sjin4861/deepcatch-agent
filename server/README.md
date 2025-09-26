# Fishing Reservation Agent Backend

Implements MVP requirements for fishing reservation AI agent.

## Stack

- FastAPI
- SQLite (SQLAlchemy)
- Twilio (simulated if credentials absent)

## Run

```
uvicorn app.main:app --reload --port 8000
```

## Endpoints

- POST /chat {"message": "..."}
- GET /status
- GET /businesses?location=부산
- POST /reservation
- POST /call
- GET /call/status
- (stubs) POST /twilio/voice, POST /twilio/status

## Chat Flow

Send user free-form Korean text. Server extracts: 날짜(YYYY-MM-DD), 시간(HH:MM), 인원, 지역, 연락처 번호.
Missing fields returned in `missing` array with Korean prompts.
When all collected, status advances to `searching` and you can start a call.

## Environment Variables (optional)

```
ACCOUNT_SID=...
AUTH_TOKEN=...
US_PHONENUMBER=+1...
```

If omitted, call operations are simulated.

## Data Loading

`app/data/businesses.csv` auto-imported at startup if businesses table empty.

## Tests

Basic tests in `app/tests/test_api.py` (requires `pytest` if you add it to deps).

## Next Steps

- Integrate real Twilio webhook logic
- Add business search ranking
- Persist multiple plans per user
- Add authentication
