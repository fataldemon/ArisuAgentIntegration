from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.orm import sessionmaker

from src.dao.dbengine import engine, Base


class Reminder(Base):
    __tablename__ = 't_reminder'
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(50), nullable=False, index=True)
    user_id = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    cron_expression = Column(String(100), nullable=True)
    remind_at = Column(DateTime, nullable=True)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    last_fired_at = Column(DateTime, nullable=True)
    next_fire_at = Column(DateTime, nullable=True)


Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


def create_reminder(group_id: str, user_id: str, content: str,
                    cron_expression: str = None, remind_at: datetime = None) -> int:
    session = Session()
    try:
        reminder = Reminder(
            group_id=group_id, user_id=user_id, content=content,
            cron_expression=cron_expression, remind_at=remind_at
        )
        session.add(reminder)
        session.commit()
        return reminder.id
    finally:
        session.close()


def get_reminder_by_id(reminder_id: int) -> Reminder:
    session = Session()
    try:
        return session.query(Reminder).filter_by(id=reminder_id).first()
    finally:
        session.close()


def list_reminders(group_id: str, user_id: str = None) -> list:
    session = Session()
    try:
        q = session.query(Reminder).filter(
            Reminder.group_id == group_id,
            Reminder.is_active == 1
        )
        if user_id:
            q = q.filter(Reminder.user_id == user_id)
        return q.order_by(Reminder.next_fire_at).all()
    finally:
        session.close()


def cancel_active_reminder(reminder_id: int) -> bool:
    session = Session()
    try:
        r = session.query(Reminder).filter_by(id=reminder_id, is_active=1).first()
        if r:
            r.is_active = 0
            session.commit()
            return True
        return False
    finally:
        session.close()


def update_reminder_fired(reminder_id: int, next_fire: datetime = None):
    session = Session()
    try:
        r = session.query(Reminder).filter_by(id=reminder_id).first()
        if r:
            r.last_fired_at = datetime.now()
            if next_fire is None:
                r.is_active = 0
            else:
                r.next_fire_at = next_fire
            session.commit()
    finally:
        session.close()


def get_all_active_reminders() -> list:
    session = Session()
    try:
        return session.query(Reminder).filter(Reminder.is_active == 1).all()
    finally:
        session.close()


def count_active_reminders(group_id: str) -> int:
    session = Session()
    try:
        return session.query(Reminder).filter(
            Reminder.group_id == group_id,
            Reminder.is_active == 1
        ).count()
    finally:
        session.close()
