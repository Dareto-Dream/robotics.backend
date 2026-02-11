# data/users_repo.py
from data.db import get_conn, release_conn

def ensure_user(user_id, username=None):
    """
    Registers the device UUID permanently.
    This is the missing identity layer your API spec requires.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO users (user_id, username)
    VALUES (%s, %s)
    ON CONFLICT (user_id)
    DO UPDATE SET
        last_seen = NOW(),
        username = COALESCE(EXCLUDED.username, users.username);
    """, (user_id, username))

    conn.commit()
    cur.close()
    release_conn(conn)
