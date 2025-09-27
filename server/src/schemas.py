from pydantic import BaseModel
from typing import Optional

class PlanBase(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    people: Optional[int] = None
    location: Optional[str] = None
    departure: Optional[str] = None

class PlanCreate(PlanBase):
    pass

class Plan(PlanBase):
    id: int
    status: str
    class Config:
        orm_mode = True

class Business(BaseModel):
    id: int
    name: str
    phone: str
    location: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    class Config:
        orm_mode = True

class ReservationCreate(BaseModel):
    success: bool
    business_name: str
    details: str
    plan_id: int

class Reservation(BaseModel):
    id: int
    success: bool
    business_name: str
    details: str
    plan_id: int
    class Config:
        orm_mode = True

class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str
    plan: Plan
    missing: list[str]
