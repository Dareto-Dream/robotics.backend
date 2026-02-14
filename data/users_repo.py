# data/users_repo.py

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
