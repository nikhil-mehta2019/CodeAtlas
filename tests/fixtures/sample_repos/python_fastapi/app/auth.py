# JWT auth helpers
import jwt

def create_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id}, "secret", algorithm="HS256")
