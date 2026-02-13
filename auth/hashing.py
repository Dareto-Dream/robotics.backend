# auth/hashing.py
#
# bcrypt password hashing.
# bcrypt silently truncates input at 72 bytes — we enforce this explicitly.

import bcrypt

MAX_BCRYPT_LEN = 72


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")[:MAX_BCRYPT_LEN]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    password_bytes = password.encode("utf-8")[:MAX_BCRYPT_LEN]
    return bcrypt.checkpw(password_bytes, hashed.encode("utf-8"))
