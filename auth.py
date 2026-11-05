import os
from functools import wraps
from dotenv import load_dotenv
from flask import request
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from repositories import UserRepository
from validators import ApiError

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("Критична помилка: змінна SECRET_KEY не знайдена у файлі .env!")

TOKEN_MAX_AGE = int(os.getenv("TOKEN_MAX_AGE", 28800))
serializer = URLSafeTimedSerializer(SECRET_KEY)


def hash_user_password(plain_password: str) -> str:
    return generate_password_hash(plain_password, method="pbkdf2:sha256", salt_length=16)


def verify_user_password(stored_hash: str, plain_password: str) -> bool:
    if stored_hash and stored_hash.startswith("pbkdf2:"):
        return check_password_hash(stored_hash, plain_password)
    return stored_hash == plain_password


def generate_auth_token(user) -> str:
    return serializer.dumps({"user_id": user.id, "role": user.role, "email": user.email})


def get_authenticated_user():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            payload = serializer.loads(token, max_age=TOKEN_MAX_AGE)
            user = UserRepository.get_by_id(payload["user_id"])
            if not user:
                raise ApiError(401, "Користувача з токена не знайдено.")
            return user
        except SignatureExpired:
            raise ApiError(401, "Термін дії токена автентифікації минув.")
        except BadSignature:
            raise ApiError(401, "Недійсний токен автентифікації.")

    body = request.get_json(silent=True) or {}
    user_id = request.headers.get("X-User-Id", type=int) or body.get("user_id")

    if user_id:
        user = UserRepository.get_by_id(int(user_id))
        if not user:
            raise ApiError(404, f"Користувача з id={user_id} не знайдено.")
        return user

    raise ApiError(401, "Необхідна автентифікація користувача.")


get_Authenticated_user = get_authenticated_user


def require_roles(*allowed_roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = get_authenticated_user()
            if user.role not in allowed_roles:
                raise ApiError(
                    403,
                    f"Доступ заборонено. Операція дозволена лише для ролей: {', '.join(allowed_roles)}."
                )
            request.current_user = user
            return func(*args, **kwargs)
        return wrapper
    return decorator