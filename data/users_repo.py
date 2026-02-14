# data/users_repo.py
from data.db import get_conn, release_conn


def ensure_user(user_id):
    """
    Ensure user exists in the main users table.
    Called after successful JWT authentication to sync with auth_users.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO users (user_id, last_seen)
    VALUES (%s, NOW())
    ON CONFLICT (user_id)
    DO UPDATE SET last_seen = NOW();
    """, (user_id,))

    conn.commit()
    cur.close()
    release_conn(conn)


def get_user_email(user_id):
    """
    Fetch user's email from auth database via the user_id.
    Returns None if user not found.
    """
    from data.auth_db import get_auth_conn, release_auth_conn
    
    conn = get_auth_conn()
    cur = conn.cursor()
    
    cur.execute("SELECT email FROM auth_users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    
    cur.close()
    release_auth_conn(conn)
    
    return row[0] if row else None
