import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "stories.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS stories (
            story_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            premise TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            version INTEGER NOT NULL DEFAULT 1,
            current_episode INTEGER NOT NULL DEFAULT 0,
            arc_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS story_bibles (
            story_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(story_id) REFERENCES stories(story_id)
        );
        CREATE TABLE IF NOT EXISTS episodes (
            story_id TEXT NOT NULL,
            episode_number INTEGER NOT NULL,
            text TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            facts_json TEXT NOT NULL DEFAULT '[]',
            used_facts_json TEXT NOT NULL DEFAULT '[]',
            characters_json TEXT NOT NULL DEFAULT '[]',
            threads_json TEXT NOT NULL DEFAULT '[]',
            hook TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            version INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (story_id, episode_number)
        );
        CREATE TABLE IF NOT EXISTS canon_facts (
            story_id TEXT NOT NULL,
            fact TEXT NOT NULL,
            source_episode INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (story_id, fact)
        );
        CREATE TABLE IF NOT EXISTS decisions (
            story_id TEXT NOT NULL,
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            feedback TEXT NOT NULL,
            scope TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id TEXT NOT NULL,
            episode_number INTEGER,
            node TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            reasoning_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

def create_story(story_id, title, premise):
    with conn() as c:
        c.execute("INSERT INTO stories(story_id,title,premise) VALUES(?,?,?)",
                  (story_id, title, premise))

def get_story(story_id):
    with conn() as c:
        r = c.execute("SELECT * FROM stories WHERE story_id=?", (story_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["arc"] = json.loads(d.pop("arc_json") or "{}")
    return d

def list_stories():
    with conn() as c:
        rows = c.execute(
            "SELECT story_id,title,premise,status,version,current_episode,updated_at "
            "FROM stories ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]

def update_story(story_id, **fields):
    allowed = {"status", "version", "current_episode", "arc_json"}
    fields = {k:v for k,v in fields.items() if k in allowed}
    if not fields:
        return
    parts, vals = [], []
    for k,v in fields.items():
        parts.append(f"{k}=?")
        vals.append(v)
    parts.append("updated_at=CURRENT_TIMESTAMP")
    vals.append(story_id)
    with conn() as c:
        c.execute(f"UPDATE stories SET {','.join(parts)} WHERE story_id=?", vals)

def save_episode(story_id, e):
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO episodes("
            "story_id,episode_number,text,summary,facts_json,used_facts_json,"
            "characters_json,threads_json,hook,status,version) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (story_id,e["episode_number"],e["text"],e.get("summary",""),
             json.dumps(e.get("facts_introduced",[])),
             json.dumps(e.get("facts_used",[])),
             json.dumps(e.get("characters_changed",[])),
             json.dumps(e.get("threads_advanced",[])),
             e.get("hook",""),e.get("status","draft"),e.get("version",1))
        )

def delete_episode(story_id, episode_number):
    with conn() as c:
        c.execute("DELETE FROM episodes WHERE story_id=? AND episode_number=?",
                  (story_id, episode_number))

def _episode_row(row):
    d = dict(row)
    d["facts_introduced"] = json.loads(d.pop("facts_json") or "[]")
    d["facts_used"] = json.loads(d.pop("used_facts_json") or "[]")
    d["characters_changed"] = json.loads(d.pop("characters_json") or "[]")
    d["threads_advanced"] = json.loads(d.pop("threads_json") or "[]")
    return d

def get_episode(story_id, episode_number):
    with conn() as c:
        r = c.execute(
            "SELECT * FROM episodes WHERE story_id=? AND episode_number=?",
            (story_id,episode_number)).fetchone()
    return _episode_row(r) if r else None

def list_episodes(story_id):
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM episodes WHERE story_id=? ORDER BY episode_number",
            (story_id,)).fetchall()
    return [_episode_row(r) for r in rows]

def add_fact(story_id, fact, source_episode):
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO canon_facts(story_id,fact,source_episode,active) "
            "VALUES(?,?,?,1)", (story_id,fact,source_episode))

def deactivate_fact(story_id, fact):
    with conn() as c:
        c.execute("UPDATE canon_facts SET active=0 WHERE story_id=? AND fact=?",
                  (story_id,fact))

def get_active_facts(story_id):
    with conn() as c:
        rows = c.execute(
            "SELECT fact FROM canon_facts WHERE story_id=? AND active=1 "
            "ORDER BY source_episode", (story_id,)).fetchall()
    return [r["fact"] for r in rows]

def add_decision(story_id, feedback, scope):
    with conn() as c:
        c.execute("INSERT INTO decisions(story_id,feedback,scope) VALUES(?,?,?)",
                  (story_id,feedback,scope))

def get_active_decisions(story_id):
    with conn() as c:
        rows = c.execute(
            "SELECT feedback FROM decisions WHERE story_id=? AND active=1 "
            "ORDER BY decision_id", (story_id,)).fetchall()
    return [r["feedback"] for r in rows]

def log_usage(story_id, episode_number, node, model, input_tokens,
              output_tokens, reasoning_tokens, cost_usd):
    with conn() as c:
        c.execute(
            "INSERT INTO usage(story_id,episode_number,node,model,input_tokens,"
            "output_tokens,reasoning_tokens,cost_usd) VALUES(?,?,?,?,?,?,?,?)",
            (story_id,episode_number,node,model,input_tokens,output_tokens,
             reasoning_tokens,cost_usd))

def get_usage(story_id):
    with conn() as c:
        rows = c.execute("SELECT * FROM usage WHERE story_id=? ORDER BY id",
                         (story_id,)).fetchall()
    return [dict(r) for r in rows]

def get_total_cost(story_id):
    with conn() as c:
        r = c.execute("SELECT COALESCE(SUM(cost_usd),0) total FROM usage WHERE story_id=?",
                      (story_id,)).fetchone()
    return float(r["total"])


def save_story_bible(story_id, payload):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO story_bibles(story_id,payload_json,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)",
                  (story_id, json.dumps(payload)))

def get_story_bible(story_id):
    with conn() as c:
        r=c.execute("SELECT payload_json FROM story_bibles WHERE story_id=?",(story_id,)).fetchone()
    return json.loads(r["payload_json"]) if r else {}
