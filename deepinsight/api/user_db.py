import sqlite3
import hashlib
import uuid
import json
from typing import Optional, Dict, Any, List

DB_PATH = "users.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    # History table (simple JSON blob for now)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS history (
        user_id TEXT,
        thread_id TEXT,
        messages TEXT,
        summary TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, thread_id)
    )
    ''')
    # Favorites table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS favorites (
        user_id TEXT,
        thread_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, thread_id)
    )
    ''')
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username: str, password: str) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        user_id = str(uuid.uuid4())
        pwd_hash = hash_password(password)
        cursor.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)", 
                       (user_id, username, pwd_hash))
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def login_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    pwd_hash = hash_password(password)
    cursor.execute("SELECT id, username FROM users WHERE username = ? AND password_hash = ?", (username, pwd_hash))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {"id": user[0], "username": user[1]}
    return None

def save_history(user_id: str, thread_id: str, messages: Any):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    msg_json = json.dumps(messages, ensure_ascii=False)
    cursor.execute('''
    INSERT INTO history (user_id, thread_id, messages, updated_at) 
    VALUES (?, ?, ?, datetime('now'))
    ON CONFLICT(user_id, thread_id) 
    DO UPDATE SET messages=excluded.messages, updated_at=excluded.updated_at
    ''', (user_id, thread_id, msg_json))
    conn.commit()
    conn.close()

def get_histories(user_id: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT h.thread_id, h.messages, h.updated_at,
               CASE WHEN f.thread_id IS NOT NULL THEN 1 ELSE 0 END as is_favorite
        FROM history h
        LEFT JOIN favorites f ON h.user_id = f.user_id AND h.thread_id = f.thread_id
        WHERE h.user_id = ?
        ORDER BY h.updated_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({
            "thread_id": r[0],
            "messages": json.loads(r[1]),
            "updated_at": r[2],
            "is_favorite": bool(r[3])
        })
    return res

def toggle_favorite(user_id: str, thread_id: str) -> bool:
    """Toggle favorite status. Returns new is_favorite state."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM favorites WHERE user_id = ? AND thread_id = ?", (user_id, thread_id))
    exists = cursor.fetchone()
    if exists:
        cursor.execute("DELETE FROM favorites WHERE user_id = ? AND thread_id = ?", (user_id, thread_id))
        is_fav = False
    else:
        cursor.execute("INSERT INTO favorites (user_id, thread_id) VALUES (?, ?)", (user_id, thread_id))
        is_fav = True
    conn.commit()
    conn.close()
    return is_fav

def delete_history(user_id: str, thread_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history WHERE user_id = ? AND thread_id = ?", (user_id, thread_id))
    cursor.execute("DELETE FROM favorites WHERE user_id = ? AND thread_id = ?", (user_id, thread_id))
    conn.commit()
    conn.close()

# Initialize on module load logic (or call explicitly)
init_db()
