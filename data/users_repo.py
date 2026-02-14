# data/users_repo.py
from data.db import get_conn, release_conn



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


def update_username(user_id, username):
    """
    Update the username for a user.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    UPDATE users 
    SET username = %s
    WHERE user_id = %s
    """, (username, user_id))

    conn.commit()
    cur.close()
    release_conn(conn)
