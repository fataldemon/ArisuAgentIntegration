from sqlalchemy import Column, String, text, Integer
from sqlalchemy.orm import sessionmaker
from src.dao.dbengine import engine, Base


class Tomb(Base):
    __tablename__ = 't_tomb'

    tomb_id = Column(Integer, primary_key=True)
    dead_user_id = Column(String(50), nullable=False)
    dead_name = Column(String(50), nullable=False)


# 创建"tomb"表
Base.metadata.create_all(engine)

# 创建一个用于数据库交互的Session类
Session = sessionmaker(bind=engine)


def add_tomb(user_id: str = "", user_name: str = ""):
    session = Session()
    dead = Tomb(dead_user_id=user_id, dead_name=user_name)
    session.add(dead)
    session.commit()
    session.close()
    print(f"▲将{user_id}:{user_name}送入墓地")


def check_death(user_id: str) -> bool:
    session = Session()
    dead = session.query(Tomb).filter_by(dead_user_id=user_id).first()
    session.close()
    if dead is not None:
        return True
    else:
        return False


def resurrection_from_graveyard(user_id: str):
    session = Session()
    dead = session.query(Tomb).filter_by(dead_user_id=user_id).first()
    session.delete(dead)
    session.commit()
    session.close()
    print(f"▲已将{dead.dead_user_id}:{dead.dead_name}从墓地复活")


def clear_graveyard():
    session = Session()
    session.execute(text("DELETE FROM t_tomb"))
    session.commit()
    session.close()
