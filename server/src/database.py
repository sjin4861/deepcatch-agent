from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import logging

DB_PATH = os.getenv("FISHING_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "fishing.db"))
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
logger = logging.getLogger(__name__)

def get_db():
    from sqlalchemy.orm import Session
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """Ensure database schema matches the latest models without manual resets."""
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "plans" not in inspector.get_table_names():
            return

        plan_columns = {column["name"] for column in inspector.get_columns("plans")}
        if "departure" not in plan_columns:
            logger.info("Adding missing 'departure' column to plans table")
            connection.execute(text("ALTER TABLE plans ADD COLUMN departure VARCHAR"))
