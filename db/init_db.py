"""Database initialization script.

Creates seed tables and inserts initial data (map, professions, weapons, status)
if they are empty. Safe to run multiple times — only inserts into empty tables.
"""

import json
import logging
import os
import sqlite3

LOG = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SEED_FILE = os.path.join(_SCRIPT_DIR, "seed_data.json")

_CREATE_TABLES = [
    """CREATE TABLE IF NOT EXISTS t_field (
        field_id INTEGER PRIMARY KEY,
        field_name VARCHAR(50) NOT NULL,
        description VARCHAR(1000)
    )""",
    """CREATE TABLE IF NOT EXISTS t_school (
        school_id INTEGER PRIMARY KEY,
        school_name VARCHAR(50) NOT NULL,
        field INTEGER NOT NULL DEFAULT 1,
        description VARCHAR(1000),
        default_p INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS t_area (
        area_id INTEGER PRIMARY KEY,
        area_name VARCHAR(50) NOT NULL,
        field INTEGER NOT NULL DEFAULT 1,
        school INTEGER NOT NULL,
        description VARCHAR(1000),
        adventure INTEGER DEFAULT 0,
        default_p INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS t_position (
        position_id INTEGER PRIMARY KEY,
        position_name VARCHAR(50) NOT NULL,
        description VARCHAR(1000),
        field INTEGER NOT NULL DEFAULT 1,
        school INTEGER NOT NULL,
        area INTEGER NOT NULL,
        size VARCHAR(10) DEFAULT '4',
        station INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS t_profession (
        prof_id INTEGER PRIMARY KEY,
        name VARCHAR(50) NOT NULL,
        description VARCHAR(200),
        hp INTEGER DEFAULT 0,
        attack INTEGER DEFAULT 0,
        defense INTEGER DEFAULT 0,
        range INTEGER DEFAULT 7
    )""",
    """CREATE TABLE IF NOT EXISTS t_weapon (
        weapon_id INTEGER PRIMARY KEY,
        weapon_name VARCHAR(50) NOT NULL,
        description VARCHAR(500),
        attack INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS t_status (
        status_id INTEGER PRIMARY KEY,
        position INTEGER NOT NULL DEFAULT 10,
        spot INTEGER NOT NULL DEFAULT 0,
        coins INTEGER NOT NULL DEFAULT 0,
        level INTEGER NOT NULL DEFAULT 1,
        profession INTEGER NOT NULL DEFAULT 0,
        attack INTEGER NOT NULL DEFAULT 100,
        defense INTEGER NOT NULL DEFAULT 10,
        exp INTEGER NOT NULL DEFAULT 0,
        hp INTEGER NOT NULL DEFAULT 100,
        hpmax INTEGER NOT NULL DEFAULT 100,
        crit INTEGER NOT NULL DEFAULT 10,
        weapon INTEGER NOT NULL DEFAULT 0,
        is_sleeping INTEGER DEFAULT 0,
        sleep_phase VARCHAR(20) DEFAULT '',
        sleep_game_name VARCHAR(50) DEFAULT '',
        sleep_hour INTEGER DEFAULT 23,
        sleep_minute INTEGER DEFAULT 0,
        wake_hour INTEGER DEFAULT 9,
        wake_minute INTEGER DEFAULT 0
    )""",
]

_SEED_TABLES = ["t_field", "t_school", "t_area", "t_position", "t_profession", "t_weapon", "t_status"]


def init_database(db_path: str) -> str:
    if not os.path.isfile(_SEED_FILE):
        return "seed_data.json not found"

    db_url = db_path
    if db_url.startswith("sqlite:///"):
        db_url = db_url[len("sqlite:///"):]

    os.makedirs(os.path.dirname(db_url) if os.path.dirname(db_url) else ".", exist_ok=True)

    conn = sqlite3.connect(db_url)
    cursor = conn.cursor()

    for ddl in _CREATE_TABLES:
        cursor.execute(ddl)

    with open(_SEED_FILE, "r", encoding="utf-8") as f:
        seed_data = json.load(f)

    seeded = []
    for table in _SEED_TABLES:
        cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
        count = cursor.fetchone()[0]
        if count > 0:
            continue
        rows = seed_data.get(table, [])
        if not rows:
            continue
        cols = list(rows[0].keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        for row in rows:
            values = [row.get(c) for c in cols]
            cursor.execute(f"INSERT INTO [{table}] ({col_names}) VALUES ({placeholders})", values)
        seeded.append(f"{table}({len(rows)})")

    conn.commit()
    conn.close()

    if seeded:
        msg = f"Seeded: {', '.join(seeded)}"
        LOG.info(msg)
        return msg
    return "Database already initialized"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = init_database(sys.argv[1])
    else:
        default_db = os.path.join(_SCRIPT_DIR, "tendou_arisu.db")
        result = init_database(default_db)
    print(result)
