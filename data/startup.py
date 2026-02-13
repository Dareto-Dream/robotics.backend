import time
import psycopg2

from data.db import get_conn as get_app_conn, init_db
from data.auth_db import get_conn as get_auth_conn, init_auth_db


def _wait(label, connector):
    last_error = None

    for attempt in range(60):
        try:
            conn = connector()
            conn.close()
            print(f"{label} database ready.")
            return
        except psycopg2.OperationalError as e:
            last_error = e
            print(f"{label} DB not ready: {type(e).__name__}: {e}")
            time.sleep(2)

    raise RuntimeError(f"{label} database never became available") from last_error


def wait_for_databases():
    print("Initializing databases...")
    init_auth_db()
    print("AUTH database initialized.")
    init_db()
    print("DATA database initialized.")

    print("Waiting for AUTH database...")
    _wait("AUTH", get_auth_conn)

    print("Waiting for DATA database...")
    _wait("DATA", get_app_conn)

    print("All databases reachable.")
