from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from . import database, models, schemas, crud, extract
from .database import Base, engine, get_db
from typing import List
import os

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Fishing Reservation Agent API")

# CORS (allow local front-end dev ports)
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:9002",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory simple call state (MVP)
CALL_STATE = {"status": "idle", "current_business": None, "sid": None}

@app.post("/chat", response_model=schemas.ChatResponse)
def chat(msg: schemas.ChatMessage, db: Session = Depends(get_db)):
    plan = crud.get_plan(db)
    entities = extract.extract_entities(msg.message)
    plan = crud.update_plan_from_dict(db, plan, entities)
    missing = crud.missing_fields(plan)
    if missing:
        reply = missing_prompt(missing)
    else:
        if plan.status == "collecting":
            plan.status = "searching"
            db.add(plan); db.commit(); db.refresh(plan)
        reply = "모든 정보가 수집되었습니다. 이제 낚시터 검색을 시작합니다. /call 엔드포인트를 호출하세요."
    return schemas.ChatResponse(reply=reply, plan=plan, missing=missing)

def missing_prompt(missing: List[str]) -> str:
    translations = {"date": "날짜(YYYY-MM-DD)", "time": "시간(HH:MM)", "people": "인원 수", "location": "지역", "phone_user": "연락처 번호"}
    ask = [translations[m] for m in missing]
    return "부족한 정보: " + ", ".join(ask)

@app.get("/status")
def status(db: Session = Depends(get_db)):
    plan = crud.get_plan(db)
    return {"plan": plan.__dict__, "call": CALL_STATE}

@app.get("/businesses", response_model=List[schemas.Business])
def list_businesses(location: str | None = None, db: Session = Depends(get_db)):
    return crud.list_businesses(db, location)

@app.post("/reservation", response_model=schemas.Reservation)
def create_reservation(res: schemas.ReservationCreate, db: Session = Depends(get_db)):
    plan = crud.get_plan(db)
    if plan.id != res.plan_id:
        raise HTTPException(status_code=400, detail="Invalid plan id")
    return crud.create_reservation(db, res)

@app.post("/call")
def start_call(db: Session = Depends(get_db)):
    plan = crud.get_plan(db)
    missing = crud.missing_fields(plan)
    if missing:
        raise HTTPException(status_code=400, detail={"missing": missing})
    plan.status = "calling"
    db.add(plan); db.commit(); db.refresh(plan)
    # TODO integrate Twilio: placeholder
    CALL_STATE.update({"status": "calling", "current_business": "Demo Fishing", "sid": "SIMULATED"})
    return {"message": "통화를 시작합니다 (시뮬레이션)", "call": CALL_STATE}

@app.get("/call/status")
def call_status():
    return CALL_STATE

# Twilio webhook stubs (to be integrated later)
@app.post("/twilio/voice")
async def twilio_voice_webhook():
    return {"message": "voice webhook stub"}

@app.post("/twilio/status")
async def twilio_status_webhook():
    return {"message": "call status webhook stub"}

# Startup hook: load businesses CSV if exists and DB empty
@app.on_event("startup")
def load_data():
    from sqlalchemy.orm import Session
    db: Session = database.SessionLocal()
    try:
        if db.query(models.Business).count() == 0:
            csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "businesses.csv")
            if os.path.exists(csv_path):
                import csv
                with open(csv_path, newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        b = models.Business(name=row['name'], phone=row['phone'], location=row['location'])
                        db.add(b)
                db.commit()
    finally:
        db.close()
