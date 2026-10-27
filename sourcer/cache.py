"""SQLite 캐시 — 한 번 조회한 키워드는 N일간 재사용 (쿠팡 조회 횟수 절약)."""
import json
import sqlite3
import time

DB = "sourcer_cache.db"


def _conn():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS kv (ns TEXT, key TEXT, value TEXT, ts REAL, PRIMARY KEY(ns, key))")
    return c


def get(ns: str, key: str, max_age_days: float):
    with _conn() as c:
        row = c.execute("SELECT value, ts FROM kv WHERE ns=? AND key=?", (ns, key)).fetchone()
    if row and time.time() - row[1] < max_age_days * 86400:
        return json.loads(row[0])
    return None


def put(ns: str, key: str, value):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO kv VALUES (?,?,?,?)",
                  (ns, key, json.dumps(value, ensure_ascii=False), time.time()))


def all_rows(ns: str):
    with _conn() as c:
        return [json.loads(v) for (v,) in c.execute("SELECT value FROM kv WHERE ns=?", (ns,))]
