from app.models import User


class UserRepository:
    def get_by_id(self, user_id: int) -> User | None:
        raise NotImplementedError
