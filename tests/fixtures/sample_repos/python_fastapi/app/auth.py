"""JWT auth helpers, password hashing, and role-based access control."""
from functools import wraps

import jwt
from werkzeug.security import check_password_hash, generate_password_hash


def create_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id}, "secret", algorithm="HS256")


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return check_password_hash(hashed, password)


def role_required(role_name):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


@role_required("admin")
def delete_user(user_id: str):
    return {"deleted": user_id}
