import os
import sys
import json
import sqlite3
import pytest

# Додаємо кореневу директорію проєкту до sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import repositories
from app import app
from validators import (
    ApiError,
    validate_email_format,
    validate_room_filters,
    validate_booking_payload,
)
from auth import hash_user_password, verify_user_password, generate_auth_token
from models import User
from repositories import UserRepository, RoomRepository, BookingRepository
from services import RoomService, BookingService


def print_api_result(title: str, response):
    """Допоміжна функція виведення результатів HTTP-запитів (видно при запуску з прапорцем -s)"""
    data = response.get_json()
    print(f"\n[ТЕСТ] {title}")
    print(f"HTTP Статус: {response.status_code}")
    print("Відповідь JSON:", json.dumps(data, ensure_ascii=False, indent=2))


# =====================================================================
# ФІКСТУРИ PYTEST (ТЕСТОВА БАЗА ДАНИХ ТА КЛІЄНТ FLASK)
# =====================================================================

@pytest.fixture
def temp_test_db(tmp_path, monkeypatch):
    """Створює чисту тестову БД SQLite із початковими аудиторіями та користувачами"""
    db_file = tmp_path / "test_booking_system.db"
    monkeypatch.setattr(repositories, "DB_PATH", str(db_file))

    conn = sqlite3.connect(str(db_file))
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE TABLE floors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            floor_number INTEGER NOT NULL UNIQUE,
            svg_map_path TEXT
        );
        CREATE TABLE rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            floor_id INTEGER NOT NULL,
            room_number TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            equipment_description TEXT,
            svg_polygon_id TEXT,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (floor_id) REFERENCES floors(id)
        );
        CREATE TABLE bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            purpose TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT,
            reminder_sent INTEGER DEFAULT 0,
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        INSERT INTO floors (id, floor_number, svg_map_path)
        VALUES (1, 3, 'static/maps/floor_3.svg');

        INSERT INTO rooms (id, floor_id, room_number, capacity, equipment_description, svg_polygon_id, is_active) VALUES
            (1, 1, '306', 30, 'Проєктор, ПК, Дошка', 'room-306', 1),
            (2, 1, '320', 25, 'Проєктор, Дошка', 'room-320', 1),
            (3, 1, '321', 20, 'ПК, Дошка', 'room-321', 1);

        INSERT INTO users (id, full_name, email, password_hash, role) VALUES
            (1, 'Адміністратор Системи', 'admin@pnu.edu.ua', 'hash_admin', 'admin'),
            (2, 'Петренко Іван Васильович', 'petrenko@pnu.edu.ua', 'hash_t1', 'teacher'),
            (3, 'Коваленко Олена Ігорівна', 'kovalenko@pnu.edu.ua', 'hash_t2', 'teacher'),
            (4, 'Студент ІПЗ-31', 'student@pnu.edu.ua', 'hash_st', 'student');
    """)
    conn.commit()
    conn.close()
    return db_file


@pytest.fixture
def client(temp_test_db):
    """Тестовий клієнт Flask, підключений до ізольованої тестової БД"""
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def get_auth_headers(user_id: int) -> dict:
    """Формує заголовки авторизації (Bearer-токен + X-User-Id) для заданого користувача"""
    user = UserRepository.get_by_id(user_id)
    token = generate_auth_token(user)
    return {
        "Authorization": f"Bearer {token}",
        "X-User-Id": str(user_id),
    }


# =====================================================================
# ЧАСТИНА 1. МОДУЛЬНЕ ТЕСТУВАННЯ (10 UNIT-ТЕСТІВ)
# =====================================================================

def test_unit_01_valid_corporate_emails():
    """Unit-тест 1: Перевірка коректних корпоративних пошт @pnu.edu.ua та @cnu.edu.ua"""
    assert validate_email_format("denys.huhliak@pnu.edu.ua") is None
    assert validate_email_format("teacher.ipz@cnu.edu.ua") is None


def test_unit_02_invalid_email_domain():
    """Unit-тест 2: Відхилення пошти зі стороннім доменом (@gmail.com)"""
    with pytest.raises(ApiError) as exc_info:
        validate_email_format("student@gmail.com")
    assert exc_info.value.status == 400


def test_unit_03_empty_email():
    """Unit-тест 3: Відхилення порожнього рядка електронної пошти"""
    with pytest.raises(ApiError) as exc_info:
        validate_email_format("")
    assert exc_info.value.status == 400


def test_unit_04_valid_room_capacity_boundaries():
    """Unit-тест 4: Граничні допустимі значення фільтра місткості (0 та 500 місць)"""
    assert validate_room_filters(0) is None
    assert validate_room_filters(500) is None


def test_unit_05_invalid_room_capacity_out_of_range():
    """Unit-тест 5: Відхилення від'ємної місткості та значення понад 500 місць"""
    with pytest.raises(ApiError) as exc_neg:
        validate_room_filters(-5)
    assert exc_neg.value.status == 400

    with pytest.raises(ApiError) as exc_over:
        validate_room_filters(501)
    assert exc_over.value.status == 400


def test_unit_06_valid_booking_payload():
    """Unit-тест 6: Валідація коректного словника даних для бронювання"""
    payload = {
        "room_id": 1,
        "user_id": 2,
        "purpose": "ІПЗ-31, Тестування ПЗ (лабораторна)",
        "start_time": "2026-11-10 09:00:00",
        "end_time": "2026-11-10 10:20:00",
    }
    assert validate_booking_payload(payload) is None


def test_unit_07_booking_payload_short_purpose():
    """Unit-тест 7: Відхилення бронювання із занадто коротким призначенням (< 5 символів)"""
    payload = {
        "room_id": 1,
        "user_id": 2,
        "purpose": "ІПЗ",
        "start_time": "2026-11-10 09:00:00",
        "end_time": "2026-11-10 10:20:00",
    }
    with pytest.raises(ApiError) as exc_info:
        validate_booking_payload(payload)
    assert exc_info.value.status == 400


def test_unit_08_booking_payload_invalid_time_order():
    """Unit-тест 8: Відхилення бронювання, де час завершення не пізніший за час початку"""
    payload = {
        "room_id": 1,
        "user_id": 2,
        "purpose": "ІПЗ-31, Лекція з програмування",
        "start_time": "2026-11-10 12:00:00",
        "end_time": "2026-11-10 10:00:00",
    }
    with pytest.raises(ApiError) as exc_info:
        validate_booking_payload(payload)
    assert exc_info.value.status == 400


def test_unit_09_password_hashing_and_verification():
    """Unit-тест 9: Перевірка PBKDF2-хешування та верифікації пароля"""
    raw_password = "SecurePassword2026"
    hashed = hash_user_password(raw_password)
    assert hashed.startswith("pbkdf2:sha256")
    assert verify_user_password(hashed, raw_password) is True
    assert verify_user_password(hashed, "WrongPassword") is False


def test_unit_10_generate_auth_token():
    """Unit-тест 10: Генерація підписаного токена сесії для моделі користувача"""
    dummy_user = User(id=5, full_name="Тестовий Викладач", email="test@pnu.edu.ua", role="teacher")
    token = generate_auth_token(dummy_user)
    assert isinstance(token, str) and len(token) > 20


# =====================================================================
# ЧАСТИНА 2. ІНТЕГРАЦІЙНЕ ТЕСТУВАННЯ БАЗИ ДАНИХ SQLite (IT-001 .. IT-003)
# =====================================================================

def test_it_001_add_and_retrieve_user_from_db(temp_test_db):
    """IT-001: Додавання нового викладача до бази даних та отримання за email"""
    created_user = UserRepository.create(
        full_name="Іван Франко",
        email="ivan.franko@pnu.edu.ua",
        password_hash=hash_user_password("TeacherPass123"),
        role="teacher",
    )
    fetched_user = UserRepository.get_by_email("ivan.franko@pnu.edu.ua")

    assert fetched_user is not None
    assert fetched_user.id == created_user.id
    assert fetched_user.full_name == "Іван Франко"
    assert fetched_user.role == "teacher"


def test_it_002_room_maintenance_status_db_integration(temp_test_db):
    """IT-002: Закриття та відкриття аудиторії на тех. обслуговування в БД"""
    updated = RoomService.set_room_active_state(room_id=1, is_active=0)
    assert updated["is_active"] == 0
    assert RoomRepository.get_by_id(1).is_active == 0

    RoomService.set_room_active_state(room_id=1, is_active=1)
    assert RoomRepository.get_by_id(1).is_active == 1


def test_it_003_booking_queue_and_auto_promotion_db_integration(temp_test_db):
    """IT-003: Створення бронювання, черги очікування та автопросування в БД"""
    t1 = UserRepository.get_by_id(2)
    t2 = UserRepository.get_by_id(3)

    slot_payload = {
        "room_id": 1,
        "purpose": "ІПЗ-31, Лабораторна робота №11",
        "start_time": "2026-11-12 09:00:00",
        "end_time": "2026-11-12 10:20:00",
    }

    res1 = BookingService.create_booking_or_queue({**slot_payload, "user_id": t1.id}, t1)
    status1 = res1.get("booking_status") or res1.get("status")
    b1_id = res1.get("booking_id") or (res1.get("booking") or {}).get("id")
    assert status1 == "confirmed"

    res2 = BookingService.create_booking_or_queue({**slot_payload, "user_id": t2.id}, t2)
    status2 = res2.get("booking_status") or res2.get("status")
    b2_id = res2.get("booking_id") or (res2.get("booking") or {}).get("id")
    assert status2 == "queued"

    BookingService.cancel_booking(b1_id, t1)
    promoted_booking = BookingRepository.get_by_id(b2_id)
    assert promoted_booking.status == "confirmed"


# =====================================================================
# ЧАСТИНА 3. ТЕСТУВАННЯ REST API (ПЕРЕВЕДЕНІ ТЕСТИ З BookingApiTestCase)
# =====================================================================

def test_api_01_get_rooms_success(client):
    """API-тест 1: Отримання списку аудиторій 3-го поверху"""
    res = client.get("/api/rooms?date=2026-10-28&slot=10:35-11:55")
    print_api_result("Отримання списку аудиторій 3-го поверху", res)

    assert res.status_code == 200
    assert len(res.get_json()) >= 3


def test_api_02_get_nonexistent_room(client):
    """API-тест 2: Запит неіснуючої аудиторії ID=999"""
    res = client.get("/api/rooms/999")
    print_api_result("2. Запит неіснуючої аудиторії ID=999", res)

    assert res.status_code == 404


def test_api_03_validation_short_purpose(client):
    """API-тест 3: Перевірка валідації — занадто коротке призначення"""
    payload = {
        "room_id": 1,
        "user_id": 2,
        "purpose": "ІПЗ",
        "start_time": "2026-11-20 10:35:00",
        "end_time": "2026-11-20 11:55:00",
    }
    res = client.post(
        "/api/bookings",
        json=payload,
        headers=get_auth_headers(2),
    )
    print_api_result("Перевірка валідації: занадто коротке призначення", res)

    assert res.status_code == 400


def test_api_04_rbac_student_forbidden(client):
    """API-тест 4: Перевірка авторизації RBAC — спроба бронювання студентом"""
    payload = {
        "room_id": 1,
        "user_id": 4,
        "purpose": "Самостійна робота студентів ІПЗ-41",
        "start_time": "2026-11-20 10:35:00",
        "end_time": "2026-11-20 11:55:00",
    }
    res = client.post(
        "/api/bookings",
        json=payload,
        headers=get_auth_headers(4),
    )
    print_api_result("Перевірка авторизації RBAC: спроба бронювання студентом", res)

    assert res.status_code == 403


def test_api_05_full_booking_and_queue_lifecycle(client):
    """API-тест 5: Повний життєвий цикл бронювання, черги, оновлення та автопросування"""
    # 1. Створення підтвердженого бронювання викладачем №1 (user_id=2)
    payload_teacher_1 = {
        "room_id": 1,
        "user_id": 2,
        "purpose": "Лекція з ІПЗ-41",
        "start_time": "2026-11-20 10:35:00",
        "end_time": "2026-11-20 11:55:00",
    }
    res_create = client.post(
        "/api/bookings",
        json=payload_teacher_1,
        headers=get_auth_headers(2),
    )
    print_api_result("Створення підтвердженого бронювання викладачем №1", res_create)
    assert res_create.status_code == 201

    create_data = res_create.get_json()
    booking_1_id = create_data.get("booking_id") or (create_data.get("booking") or {}).get("id")
    booking_1_status = create_data.get("booking_status") or create_data.get("status")
    assert booking_1_status == "confirmed"

    # 2. Блокування повторного запису в чергу тим самим викладачем
    res_duplicate = client.post(
        "/api/bookings",
        json=payload_teacher_1,
        headers=get_auth_headers(2),
    )
    print_api_result("Блокування повторного запису в чергу тим самим викладачем", res_duplicate)
    assert res_duplicate.status_code == 409

    # 3. Постановка другого викладача (user_id=3) в чергу очікування
    payload_teacher_2 = {
        "room_id": 1,
        "user_id": 3,
        "purpose": "Консультація з курсового проєктування",
        "start_time": "2026-11-20 10:35:00",
        "end_time": "2026-11-20 11:55:00",
    }
    res_queue = client.post(
        "/api/bookings",
        json=payload_teacher_2,
        headers=get_auth_headers(3),
    )
    print_api_result("Постановка другого викладача в чергу очікування", res_queue)
    assert res_queue.status_code == 201

    queue_data = res_queue.get_json()
    booking_2_id = queue_data.get("booking_id") or (queue_data.get("booking") or {}).get("id")
    booking_2_status = queue_data.get("booking_status") or queue_data.get("status")
    assert booking_2_status == "queued"

    # 4. Часткове оновлення призначення бронювання (PATCH)
    res_patch = client.patch(
        f"/api/bookings/{booking_1_id}",
        json={"purpose": "Лекція з ІПЗ-41 (оновлено)"},
        headers=get_auth_headers(2),
    )
    print_api_result("Часткове оновлення бронювання", res_patch)
    assert res_patch.status_code == 200

    # 5. Скасування основного бронювання та автоматичне просування черги (DELETE)
    res_delete = client.delete(
        f"/api/bookings/{booking_1_id}",
        headers=get_auth_headers(2),
    )
    print_api_result("Скасування бронювання та автопросування черги", res_delete)
    assert res_delete.status_code == 200

    delete_data = res_delete.get_json()
    if "promoted_booking_id" in delete_data:
        assert delete_data["promoted_booking_id"] == booking_2_id
    assert BookingRepository.get_by_id(booking_2_id).status == "confirmed"