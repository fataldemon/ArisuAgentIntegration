import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Sequence

current_working_dir = Path(__file__).parent.parent

sqlconn = f"sqlite:///{current_working_dir}/db/tendou_arisu.db"
engine = create_engine(sqlconn, echo=False)

