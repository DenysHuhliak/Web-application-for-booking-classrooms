import os
import sys
import unittest
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
from repositories import get_db_connection


class BookingApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()
        cls._cleanup_test_slot()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_test_slot()

    @staticmethod
    def _cleanup_test_slot():
        conn = get_db_connection()
        conn.execute("DELETE FROM bookings WHERE start_time LIKE '2026-11-20%'")
        conn.commit()
        conn.close()

    def _print_result(self, title, response):
        data = response.get_json()
        print(f"\n[ТЕСТ] {title}")
        print(f"HTTP Статус: {response.status_code}")
        print("Відповідь JSON:", json.dumps(data, ensure_ascii=False, indent=2))

    def test_01_get_rooms_success(self):
        res = self.client.get("/api/rooms?date=2026-10-28&slot=10:35-11:55")
        self._print_result("Отримання списку аудиторій 3-го поверху", res)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(len(res.get_json()) >= 3)

    def test_02_get_nonexistent_room(self):
        res = self.client.get("/api/rooms/999")
        self._print_result("2. Запит неіснуючої аудиторії ID=999", res)
        self.assertEqual(res.status_code, 404)

    def test_03_validation_short_purpose(self):
        payload = {
            "room_id": 1,
            "user_id": 2,
            "purpose": "ІПЗ", 
            "start_time": "2026-11-20 10:35:00",
            "end_time": "2026-11-20 11:55:00"
        }
        res = self.client.post(
            "/api/bookings",
            json=payload,
            headers={"X-User-Id": "2"}
        )
        self._print_result("Перевірка валідації: занадто коротке призначення", res)
        self.assertEqual(res.status_code, 400)

    def test_04_rbac_student_forbidden(self):
        payload = {
            "room_id": 1,
            "user_id": 4,
            "purpose": "Самостійна робота студентів ІПЗ-41",
            "start_time": "2026-11-20 10:35:00",
            "end_time": "2026-11-20 11:55:00"
        }
        res = self.client.post(
            "/api/bookings",
            json=payload,
            headers={"X-User-Id": "4"} 
        )
        self._print_result("Перевірка авторизації RBAC: спроба бронювання студентом", res)
        self.assertEqual(res.status_code, 403)

    def test_05_full_booking_and_queue_lifecycle(self):
        payload_teacher_1 = {
            "room_id": 1,
            "user_id": 2,
            "purpose": "Лекція з ІПЗ-41",
            "start_time": "2026-11-20 10:35:00",
            "end_time": "2026-11-20 11:55:00"
        }
        res_create = self.client.post(
            "/api/bookings",
            json=payload_teacher_1,
            headers={"X-User-Id": "2"}
        )
        self._print_result("Створення підтвердженого бронювання викладачем №1", res_create)
        self.assertEqual(res_create.status_code, 201)
        booking_1_id = res_create.get_json()["booking_id"]
        self.assertEqual(res_create.get_json()["booking_status"], "confirmed")

        res_duplicate = self.client.post(
            "/api/bookings",
            json=payload_teacher_1,
            headers={"X-User-Id": "2"}
        )
        self._print_result("Блокування повторного запису в чергу тим самим викладачем", res_duplicate)
        self.assertEqual(res_duplicate.status_code, 409)

        payload_teacher_2 = {
            "room_id": 1,
            "user_id": 3,
            "purpose": "Консультація з курсового проєктування",
            "start_time": "2026-11-20 10:35:00",
            "end_time": "2026-11-20 11:55:00"
        }
        res_queue = self.client.post(
            "/api/bookings",
            json=payload_teacher_2,
            headers={"X-User-Id": "3"}
        )
        self._print_result("Постановка другого викладача в чергу очікування", res_queue)
        self.assertEqual(res_queue.status_code, 201)
        booking_2_id = res_queue.get_json()["booking_id"]
        self.assertEqual(res_queue.get_json()["booking_status"], "queued")

        res_patch = self.client.patch(
            f"/api/bookings/{booking_1_id}",
            json={"purpose": "Лекція з ІПЗ-41"},
            headers={"X-User-Id": "2"}
        )
        self._print_result("Часткове оновлення бронювання", res_patch)
        self.assertEqual(res_patch.status_code, 200)

        res_delete = self.client.delete(
            f"/api/bookings/{booking_1_id}",
            headers={"X-User-Id": "2"}
        )
        self._print_result("Скасування бронювання та автопросування черги", res_delete)
        self.assertEqual(res_delete.status_code, 200)
        self.assertEqual(res_delete.get_json()["promoted_booking_id"], booking_2_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)