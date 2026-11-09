from validators import ApiError, validate_booking_payload, validate_room_filters, validate_email_format
from repositories import (
    AbstractUserRepository,
    AbstractRoomRepository,
    AbstractBookingRepository,
    UserRepository,
    RoomRepository,
    BookingRepository,
)
from auth import generate_auth_token, verify_user_password, hash_user_password
from email_service import EmailNotificationService


class AuthService:
    user_repo: AbstractUserRepository = UserRepository

    @classmethod
    def login_user(cls, data: dict) -> dict:
        email = str(data.get("email", "")).strip()
        password = str(data.get("password", "")).strip()

        validate_email_format(email)
        if not password:
            raise ApiError(400, "Поле пароля є обов'язковим.")

        user = cls.user_repo.get_by_email(email)
        if not user or not verify_user_password(user.password_hash, password):
            raise ApiError(401, "Невірна електронна пошта або пароль.")

        return {
            "status": 200,
            "message": "Автентифікація успішна.",
            "token": generate_auth_token(user),
            "user": user.to_dict()
        }

    @classmethod
    def register_user(cls, data: dict) -> dict:
        full_name = str(data.get("full_name", "")).strip()
        email = str(data.get("email", "")).strip()
        password = str(data.get("password", "")).strip()
        role = str(data.get("role", "student")).strip()

        validate_email_format(email)
        if not (3 <= len(full_name) <= 100):
            raise ApiError(400, "ПІБ користувача повинно містити від 3 до 100 символів.")
        if len(password) < 8:
            raise ApiError(400, "Пароль повинен містити щонайменше 8 символів.")
        if role not in ("admin", "teacher", "student"):
            raise ApiError(400, "Некоректна роль користувача.")
        if cls.user_repo.get_by_email(email):
            raise ApiError(409, "Користувач із такою корпоративною поштою вже зареєстрований.")

        new_user = cls.user_repo.create(full_name, email, hash_user_password(password), role)
        return {
            "status": 201,
            "success": True,
            "message": f"Користувача «{new_user.full_name}» успішно зареєстровано!",
            "token": generate_auth_token(new_user),
            "user": new_user.to_dict()
        }


class RoomService:
    room_repo: AbstractRoomRepository = RoomRepository
    booking_repo: AbstractBookingRepository = BookingRepository

    @classmethod
    def get_rooms_with_occupancy(cls, date_str: str, time_slot: str, min_capacity: int, equipment: str, current_user=None):
        validate_room_filters(min_capacity)
        if "-" not in time_slot:
            raise ApiError(400, "Некоректний формат часового слоту пари.")

        start_t, end_t = time_slot.split("-")
        start_dt, end_dt = f"{date_str} {start_t}:00", f"{date_str} {end_t}:00"
        req_equip = [item.strip().lower() for item in equipment.split(",") if item.strip()]

        result = []
        for r in cls.room_repo.get_all_by_floor(3):
            active_booking = cls.booking_repo.get_confirmed_for_slot(r.id, start_dt, end_dt)
            next_queued = cls.booking_repo.get_next_queued_for_slot(r.id, start_dt, end_dt)
            room_eq = (r.equipment_description or "").lower()

            status = "closed" if r.is_active == 0 else ("occupied" if active_booking else "free")
            matches = r.capacity >= min_capacity and all(eq in room_eq for eq in req_equip)

            result.append({
                **r.to_dict(),
                "status": status,
                "current_booking": active_booking if (status == "occupied" and current_user) else None,
                "queue_count": cls.booking_repo.count_queued_for_slot(r.id, start_dt, end_dt),
                "first_in_queue": next_queued.teacher_name if (next_queued and current_user) else None,
                "matches_filter": matches
            })

        return result

    @classmethod
    def set_room_active_state(cls, room_id: int, is_active: int) -> dict:
        if is_active not in (0, 1):
            raise ApiError(400, "Поле is_active приймає лише значення 0 або 1.")
        if not cls.room_repo.get_by_id(room_id):
            raise ApiError(404, f"Аудиторію з id={room_id} не знайдено.")

        cls.room_repo.update_status(room_id, is_active)
        return cls.room_repo.get_by_id(room_id).to_dict()


class BookingService:
    room_repo: AbstractRoomRepository = RoomRepository
    booking_repo: AbstractBookingRepository = BookingRepository

    @classmethod
    def _get_authorized_booking(cls, booking_id: int, current_user):
        booking = cls.booking_repo.get_by_id(booking_id)
        if not booking:
            raise ApiError(404, f"Бронювання з id={booking_id} не знайдено.")
        if current_user.role != "admin" and booking.user_id != current_user.id:
            raise ApiError(403, "Ви можете змінювати або скасовувати лише власні бронювання.")
        return booking

    @classmethod
    def list_bookings(cls, current_user):
        bookings = cls.booking_repo.get_all()
        if current_user.role == "admin":
            return [b.to_dict() for b in bookings]
        if current_user.role == "teacher":
            return [b.to_dict() for b in bookings if b.user_id == current_user.id]
        raise ApiError(403, "Доступ дозволено лише викладачам та адміністраторам.")

    @classmethod
    def create_booking_or_queue(cls, data: dict, current_user) -> dict:
        validate_booking_payload(data)
        room = cls.room_repo.get_by_id(data["room_id"])
        if not room:
            raise ApiError(404, "Обрану аудиторію не знайдено.")
        if room.is_active == 0:
            raise ApiError(409, "Аудиторія тимчасово зачинена на технічне обслуговування.")

        start_time, end_time = data["start_time"], data["end_time"]

        user_existing = cls.booking_repo.get_user_existing_booking_in_slot(
            room.id, current_user.id, start_time, end_time
        )
        if user_existing:
            if user_existing["status"] == "confirmed":
                raise ApiError(409, "Ви вже забронювали цю аудиторію на обрану пару.")
            raise ApiError(409, "Ви вже перебуваєте в черзі очікування на цю аудиторію на обрану пару.")

        existing = cls.booking_repo.get_confirmed_for_slot(room.id, start_time, end_time)
        status = "queued" if existing else "confirmed"

        new_id = cls.booking_repo.create(
            room_id=room.id,
            user_id=current_user.id,
            purpose=data["purpose"].strip(),
            start_time=start_time,
            end_time=end_time,
            status=status
        )
        new_booking = cls.booking_repo.get_by_id(new_id)

        if data.get("notify_email", True) and new_booking:
            if EmailNotificationService.send_booking_created(new_booking):
                cls.booking_repo.mark_reminder_sent(new_id)
                new_booking = cls.booking_repo.get_by_id(new_id)

        msg = (
            f"Аудиторія №{room.room_number} вже зайнята. Вашу заявку додано в чергу очікування!"
            if status == "queued"
            else f"Аудиторію №{room.room_number} успішно заброньовано!"
        )
        return {"status": status, "message": msg, "booking": new_booking.to_dict()}

    @classmethod
    def update_booking_purpose(cls, booking_id: int, new_purpose: str, current_user) -> dict:
        purpose = str(new_purpose or "").strip()
        if not (5 <= len(purpose) <= 200):
            raise ApiError(400, "Призначення заняття повинно містити від 5 до 200 символів.")

        cls._get_authorized_booking(booking_id, current_user)
        cls.booking_repo.update_purpose(booking_id, purpose)
        return cls.booking_repo.get_by_id(booking_id).to_dict()

    @classmethod
    def cancel_booking(cls, booking_id: int, current_user) -> dict:
        booking = cls._get_authorized_booking(booking_id, current_user)
        is_admin_cancel = (current_user.role == "admin" and booking.user_id != current_user.id)

        promoted_id = cls.booking_repo.delete_and_promote_next(booking)

        EmailNotificationService.send_booking_cancelled(
            booking=booking,
            cancelled_by_admin=is_admin_cancel,
            admin_name=current_user.full_name
        )

        promoted_info = ""
        if promoted_id:
            promoted = cls.booking_repo.get_by_id(promoted_id)
            if promoted:
                if EmailNotificationService.send_queue_promoted(promoted):
                    cls.booking_repo.mark_reminder_sent(promoted_id)
                promoted_info = f" Заявку викладача «{promoted.teacher_name}» автоматично переведено з черги у статус підтвердженої."

        base_msg = (
            f"Бронювання викладача «{booking.teacher_name}» скасовано адміністратором."
            if is_admin_cancel
            else "Бронювання скасовано."
        )
        return {"status": 200, "message": f"{base_msg}{promoted_info}"}