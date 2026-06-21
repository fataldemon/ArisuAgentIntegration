import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Sequence

load_dotenv()

current_working_dir = Path(__file__).parent.parent
_default_db = f"sqlite:///{current_working_dir}/db/tendou_arisu.db"
sqlconn = os.environ.get("SQLALCHEMY_DATABASE_URL", _default_db)
engine = create_engine(sqlconn, echo=False)
