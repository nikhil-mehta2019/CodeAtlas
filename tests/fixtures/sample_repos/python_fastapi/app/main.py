from fastapi import Depends, FastAPI

from app.repository import UserRepository

app = FastAPI()


def get_user_repository() -> UserRepository:
    return UserRepository()


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/users/{user_id}")
def get_user(user_id: int, repo: UserRepository = Depends(get_user_repository)):
    return repo.get_by_id(user_id)

@app.post("/webhooks/stripe")
def stripe_webhook():
    return {"received": True}
