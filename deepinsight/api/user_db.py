import sqlite3
import hashlib
import hmac
import secrets
import base64
import uuid
import json
import time
import os
from typing import Optional, Dict, Any, List

DB_PATH = "users.db"

_TOKEN_STORE: dict = {}
_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60
_AUTH_SECRET = os.getenv("AUTH_SECRET", "dev_secret_change_me")


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(user_id: str) -> str:
    payload = {
        "uid": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + _TOKEN_TTL_SECONDS,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_AUTH_SECRET.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    token = f"{_base64url_encode(payload_bytes)}.{_base64url_encode(signature)}"
    _TOKEN_STORE[token] = user_id
    return token


def verify_token(token: str) -> Optional[str]:
    """Returns user_id if valid, else None."""
    if not token:
        return None

    if token in _TOKEN_STORE:
        return _TOKEN_STORE.get(token)

    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload_bytes = _base64url_decode(payload_b64)
        expected = hmac.new(_AUTH_SECRET.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
        actual = _base64url_decode(signature_b64)
        if not hmac.compare_digest(actual, expected):
            return None
        payload = json.loads(payload_bytes.decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload.get("uid")
    except Exception:
        return None


def revoke_token(token: str):
    _TOKEN_STORE.pop(token, None)

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
        title TEXT DEFAULT 'Untitled Session',
        message_count INT DEFAULT 0,
        messages TEXT,
        summary TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

PBKDF2_ITERATIONS = 120_000
SALT_BYTES = 16


def _pbkdf2_hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS
    )


def hash_password(password: str) -> str:
    """Create a salted password hash using PBKDF2."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _pbkdf2_hash(password, salt)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify password against PBKDF2 hash or legacy SHA-256 hash."""
    if "$" in stored:
        try:
            salt_b64, digest_b64 = stored.split("$", 1)
            salt = base64.b64decode(salt_b64.encode())
            expected = base64.b64decode(digest_b64.encode())
            actual = _pbkdf2_hash(password, salt)
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False
    # Legacy SHA-256 fallback
    return stored == hashlib.sha256(password.encode("utf-8")).hexdigest()

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
    cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    user_id, uname, pwd_hash = row
    if not verify_password(password, pwd_hash):
        conn.close()
        return None

    # Upgrade legacy hashes on successful login
    if "$" not in pwd_hash:
        try:
            new_hash = hash_password(password)
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
            conn.commit()
        except Exception:
            pass

    conn.close()
    token = create_token(user_id)
    return {"id": user_id, "username": uname, "token": token}

def generate_session_title(messages: List[Dict[str, Any]]) -> str:
    """
    从第一个用户消息生成会话标题
    - 长度限制：60 字符
    - 如果无user消息或为空，返回默认标题
    """
    if not messages or not isinstance(messages, list):
        return "Untitled Session"
    
    # 找第一个 user 消息
    first_user_msg = None
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            first_user_msg = msg.get("content", "").strip()
            break
    
    if not first_user_msg:
        return "Untitled Session"
    
    # 截断到 60 字符
    title = first_user_msg[:60]
    
    # 如果被截断，添加省略号
    if len(first_user_msg) > 60:
        title = title.rstrip() + "..."
    
    return title

def save_history(user_id: str, thread_id: str, messages: Any):
    """
    保存用户的研究历史
    - 自动从第一个 user 消息生成 title
    - 自动计算 message_count
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    msg_json = json.dumps(messages, ensure_ascii=False)
    
    # 生成标题和计数
    title = generate_session_title(messages)
    message_count = len(messages) if isinstance(messages, list) else 0
    
    cursor.execute('''
    INSERT INTO history (user_id, thread_id, title, message_count, messages, updated_at) 
    VALUES (?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(user_id, thread_id) 
    DO UPDATE SET 
        title=excluded.title,
        message_count=excluded.message_count,
        messages=excluded.messages,
        updated_at=excluded.updated_at
    ''', (user_id, thread_id, title, message_count, msg_json))
    conn.commit()
    conn.close()

def get_histories(user_id: str) -> list:
    """获取用户的所有历史记录，包括标题和消息数"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT h.thread_id, h.title, h.message_count, h.messages, h.updated_at,
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
            "title": r[1] or "Untitled Session",
            "message_count": r[2] or 0,
            "messages": json.loads(r[3]),
            "updated_at": r[4],
            "is_favorite": bool(r[5])
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
