# data/teams_repo.py
import secrets
from data.db import get_conn, release_conn

JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_join_code():
    return "".join(secrets.choice(JOIN_ALPHABET) for _ in range(6))


def get_user_team(user_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT t.team_code, t.name, t.team_number, t.description,
           m.role, m.display_name, m.bio, m.profile_pic_url, m.subteam, m.joined_at
    FROM memberships m
    JOIN teams t ON t.team_code = m.team_code
    WHERE m.user_id=%s AND m.is_active=TRUE;
    """, (user_id,))

    row = cur.fetchone()

    cur.close()
    release_conn(conn)
    return row


def create_team(user_id, name, team_number, display_name):
    conn = get_conn()
    cur = conn.cursor()

    code = generate_join_code()

    cur.execute("""
    INSERT INTO teams (team_code,name,team_number,created_by)
    VALUES (%s,%s,%s,%s)
    """, (code, name, team_number, user_id))

    cur.execute("""
    INSERT INTO memberships (user_id,team_code,role,display_name)
    VALUES (%s,%s,'owner',%s)
    """, (user_id, code, display_name))

    conn.commit()
    cur.close()
    release_conn(conn)

    return code
