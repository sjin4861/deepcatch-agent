from sqlalchemy import Column, Integer, String, Boolean, Text, Float
from .database import Base

class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, nullable=True)
    time = Column(String, nullable=True)
    people = Column(Integer, nullable=True)
    location = Column(String, nullable=True)
    departure = Column(String, nullable=True)
    status = Column(String, default="collecting")  # collecting, searching, calling, completed

class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    phone = Column(String, index=True)
    location = Column(String, index=True)
    address = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, index=True)
    success = Column(Boolean, default=False)
    business_name = Column(String)
    details = Column(Text)
    plan_id = Column(Integer)
