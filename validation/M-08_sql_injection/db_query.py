"""Simple user lookup — queries a SQLite database by username."""
import sqlite3


def get_user(db_path: str, username: str) -> dict | None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = f"SELECT id, username, email FROM users WHERE username = '{username}'"
    cursor.execute(query)
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return {"id": row[0], "username": row[1], "email": row[2]}


def get_users_by_role(db_path: str, role: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT id, username FROM users WHERE role = '{role}' ORDER BY username"
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "username": r[1]} for r in rows]


def delete_user(db_path: str, username: str) -> bool:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM users WHERE username = '{username}'")
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0
