from sqlalchemy import text
from sqlalchemy.orm import Session


def check_database_health(db: Session) -> bool:
    return db.execute(text("select 1")).scalar_one() == 1
