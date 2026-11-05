import re
from datetime import datetime

class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def validate_booking_payload(data: dict):
    if not data or not isinstance(data, dict):
        raise ApiError(400, "Тіло запиту повинно бути коректним JSON-об'єктом.")

    room_id = data.get("room_id")
    user_id = data.get("user_id")
    purpose = str(data.get("purpose", "")).strip()
    start_time = str(data.get("start_time", "")).strip()
    end_time = str(data.get("end_time", "")).strip()

    if not isinstance(room_id, int) or room_id <= 0:
        raise ApiError(400, "Некоректний ідентифікатор аудиторії (room_id).")
    if not isinstance(user_id, int) or user_id <= 0:
        raise ApiError(400, "Некоректний ідентифікатор користувача (user_id).")

    if len(purpose) < 5 or len(purpose) > 200:
        raise ApiError(
            400,
            "Призначення заняття повинно містити від 5 до 200 символів."
        )

    try:
        dt_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        dt_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ApiError(
            400,
            "Некоректний формат часу. Очікується YYYY-MM-DD HH:MM:SS."
        )

    if dt_end <= dt_start:
        raise ApiError(
            400,
            "Час завершення пари повинен бути пізнішим за час початку."
        )


def validate_room_filters(capacity: int):
    if capacity < 0 or capacity > 500:
        raise ApiError(
            400,
            "Мінімальна місткість повинна бути в діапазоні від 0 до 500 місць."
        )


def validate_email_format(email: str):
    pattern = r"^[a-zA-Z0-9_.+-]+@(pnu|cnu)\.edu\.ua$"
    if not re.match(pattern, (email or "").strip(), re.IGNORECASE):
        raise ApiError(
            400,
            "Електронна адреса повинна належати корпоративному домену @pnu.edu.ua."
        )