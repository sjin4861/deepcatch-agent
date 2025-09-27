from sqlalchemy.orm import Session
from . import models, schemas
from typing import List, Optional

REQUIRED_FIELDS = ["date", "time", "people", "location", "departure"]

def get_plan(db: Session) -> models.Plan:
    plan = db.query(models.Plan).first()
    if not plan:
        plan = models.Plan()
        db.add(plan)
        db.commit()
        db.refresh(plan)
    return plan

def update_plan_from_dict(db: Session, plan: models.Plan, data: dict) -> models.Plan:
    changed = False
    for field, value in data.items():
        if value is not None and getattr(plan, field) != value:
            setattr(plan, field, value)
            changed = True
    if changed:
        db.add(plan)
        db.commit()
        db.refresh(plan)
    return plan

def missing_fields(plan: models.Plan) -> List[str]:
    missing = []
    for field in REQUIRED_FIELDS:
        if getattr(plan, field) in (None, ""):
            missing.append(field)
    return missing

def list_businesses(db: Session, location: Optional[str] = None):
    q = db.query(models.Business)
    if location:
        q = q.filter(models.Business.location == location)
    return q.all()

def create_reservation(db: Session, data: schemas.ReservationCreate):
    res = models.Reservation(**data.dict())
    db.add(res)
    db.commit()
    db.refresh(res)
    return res
