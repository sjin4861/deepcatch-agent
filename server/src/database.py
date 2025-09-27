from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import csv
import logging
from typing import Dict, Any
logger = logging.getLogger(__name__)

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

def _normalize_location(raw: str | None) -> str:
    if not raw:
        return "구룡포"
    r = raw.strip()
    lower = r.lower()
    mapping = {
        "guryongpo": "구룡포",
        "구룡포": "구룡포",
    }
    return mapping.get(lower, r)


def reseed_businesses(*, force: bool = False, normalize: bool = True) -> Dict[str, Any]:  # pragma: no cover - helper
    """(Re)seed businesses from CSV.

    force=True 이면 기존 레코드를 모두 삭제 후 CSV 기준으로 재구성.
    force=False 이면 없는 name 추가 / 기존 name 은 phone/location 업데이트 (upsert 느낌).
    normalize=True 면 location 정규화 매핑 적용.
    """
    from . import models
    session = SessionLocal()
    added = 0
    updated = 0
    deleted = 0
    try:
        csv_path = os.path.join(os.path.dirname(__file__), 'data', 'businesses.csv')
        if not os.path.exists(csv_path):
            logger.warning(f"[reseed] CSV 파일을 찾지 못했습니다: {csv_path}")
            return {"added": 0, "updated": 0, "deleted": 0, "path": csv_path, "error": "csv_not_found"}

        rows: list[dict[str, str]] = []
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        logger.info(f"[reseed] CSV 로드 {len(rows)}행 (force={force}, normalize={normalize})")

        if force:
            deleted = session.query(models.Business).delete()
            session.commit()
            logger.info(f"[reseed] 기존 레코드 {deleted}건 삭제")

        existing_by_name: Dict[str, models.Business] = {b.name: b for b in session.query(models.Business).all()}

        for row in rows:
            name = (row.get('name') or '').strip()
            phone = (row.get('phone') or '').strip()
            location = (row.get('location') or '').strip()
            if not name or not phone:
                continue
            if normalize:
                location = _normalize_location(location)
            if name in existing_by_name:
                biz = existing_by_name[name]
                changed = False
                if phone and biz.phone != phone:
                    biz.phone = phone
                    changed = True
                if location and biz.location != location:
                    biz.location = location
                    changed = True
                if changed:
                    updated += 1
            else:
                session.add(models.Business(name=name, phone=phone, location=location or '구룡포'))
                added += 1
        session.commit()
        return {"added": added, "updated": updated, "deleted": deleted, "path": csv_path}
    except Exception as e:  # pragma: no cover
        logger.error(f"[reseed] 실패: {e}", exc_info=True)
        session.rollback()
        return {"added": added, "updated": updated, "deleted": deleted, "error": str(e)}
    finally:
        session.close()


def seed_businesses_if_needed():  # pragma: no cover - simple startup helper
    from . import models
    session = SessionLocal()
    try:
        count = session.query(models.Business).count()
        if count == 0:
            summary = reseed_businesses(force=False, normalize=True)
            logger.info(f"[seed] 초기 시드 완료: {summary}")
        else:
            logger.info(f"[seed] 기존 비즈니스 레코드 {count}건 존재하여 시드 생략")
    finally:
        session.close()

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
