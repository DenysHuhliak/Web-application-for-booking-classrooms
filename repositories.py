import sqlite3
from typing import List, Optional
from models import User, Room, Booking

DB_PATH = "booking_system.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_one(query: str, params: tuple = ()):
    conn = get_db_connection()
    try:
        return conn.execute(query, params).fetchone()
    finally:
        conn.close()


def _fetch_all(query: str, params: tuple = ()):
    conn = get_db_connection()
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


class UserRepository:
    _SELECT = "SELECT id, full_name, email, role, password_hash FROM users"

    @staticmethod
    def create(full_name: str, email: str, password_hash: str, role: str) -> User:
        conn = get_db_connection()
        try:
            cur = conn.execute(
                "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (full_name, email, password_hash, role)
            )
            conn.commit()
            return User(id=cur.lastrowid, full_name=full_name, email=email, role=role)
        finally:
            conn.close()

    @staticmethod
    def get_by_id(user_id: int) -> Optional[User]:
        row = _fetch_one(f"{UserRepository._SELECT} WHERE id = ?", (user_id,))
        return User(**dict(row)) if row else None

    @staticmethod
    def get_by_email(email: str) -> Optional[User]:
        row = _fetch_one(f"{UserRepository._SELECT} WHERE email = ?", (email,))
        return User(**dict(row)) if row else None


class RoomRepository:
    _SELECT = """
        SELECT r.id, r.floor_id, r.room_number, r.capacity,
               r.equipment_description, r.svg_polygon_id, r.is_active,
               f.floor_number
        FROM rooms r
        JOIN floors f ON r.floor_id = f.id
    """

    @staticmethod
    def get_all_by_floor(floor_number: int = 3) -> List[Room]:
        rows = _fetch_all(
            f"{RoomRepository._SELECT} WHERE f.floor_number = ? ORDER BY r.room_number ASC",
            (floor_number,)
        )
        return [Room(**dict(r)) for r in rows]

    @staticmethod
    def get_by_id(room_id: int) -> Optional[Room]:
        row = _fetch_one(f"{RoomRepository._SELECT} WHERE r.id = ?", (room_id,))
        return Room(**dict(row)) if row else None

    @staticmethod
    def update_status(room_id: int, is_active: int) -> bool:
        conn = get_db_connection()
        try:
            cur = conn.execute("UPDATE rooms SET is_active = ? WHERE id = ?", (is_active, room_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


class BookingRepository:
    _SELECT = """
        SELECT b.id, b.room_id, b.user_id, b.purpose, b.start_time, b.end_time,
               b.status, b.created_at, b.reminder_sent,
               r.room_number, u.full_name AS teacher_name, u.email
        FROM bookings b
        JOIN rooms r ON b.room_id = r.id
        JOIN users u ON b.user_id = u.id
    """

    @staticmethod
    def get_all() -> List[Booking]:
        rows = _fetch_all(
            f"{BookingRepository._SELECT} WHERE b.status != 'cancelled' ORDER BY b.start_time ASC, b.created_at ASC"
        )
        return [Booking(**dict(r)) for r in rows]

    @staticmethod
    def get_by_id(booking_id: int) -> Optional[Booking]:
        row = _fetch_one(f"{BookingRepository._SELECT} WHERE b.id = ?", (booking_id,))
        return Booking(**dict(row)) if row else None

    @staticmethod
    def get_confirmed_for_slot(room_id: int, start_dt: str, end_dt: str) -> Optional[dict]:
        row = _fetch_one("""
            SELECT b.id, b.user_id, b.purpose, b.start_time, b.end_time,
                   u.full_name AS teacher_name
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            WHERE b.room_id = ? AND b.status = 'confirmed' AND b.start_time < ? AND b.end_time > ?
        """, (room_id, end_dt, start_dt))
        return dict(row) if row else None

    @staticmethod
    def get_user_existing_booking_in_slot(room_id: int, user_id: int, start_dt: str, end_dt: str) -> Optional[dict]:
        row = _fetch_one("""
            SELECT id, status FROM bookings
            WHERE room_id = ? AND user_id = ? AND status IN ('confirmed', 'queued')
              AND start_time < ? AND end_time > ?
        """, (room_id, user_id, end_dt, start_dt))
        return dict(row) if row else None

    @staticmethod
    def count_queued_for_slot(room_id: int, start_dt: str, end_dt: str) -> int:
        row = _fetch_one("""
            SELECT COUNT(*) AS cnt FROM bookings
            WHERE room_id = ? AND status = 'queued' AND start_time < ? AND end_time > ?
        """, (room_id, end_dt, start_dt))
        return row["cnt"] if row else 0

    @staticmethod
    def get_next_queued_for_slot(room_id: int, start_dt: str, end_dt: str) -> Optional[Booking]:
        row = _fetch_one(f"""
            {BookingRepository._SELECT}
            WHERE b.room_id = ? AND b.status = 'queued' AND b.start_time < ? AND b.end_time > ?
            ORDER BY b.created_at ASC, b.id ASC
            LIMIT 1
        """, (room_id, end_dt, start_dt))
        return Booking(**dict(row)) if row else None

    @staticmethod
    def create(room_id: int, user_id: int, purpose: str, start_time: str, end_time: str, status: str) -> int:
        conn = get_db_connection()
        try:
            cur = conn.execute("""
                INSERT INTO bookings (room_id, user_id, purpose, start_time, end_time, status, created_at, reminder_sent)
                VALUES (?, ?, ?, ?, ?, ?, DATETIME('now'), 0)
            """, (room_id, user_id, purpose, start_time, end_time, status))
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    @staticmethod
    def update_purpose(booking_id: int, purpose: str) -> bool:
        conn = get_db_connection()
        try:
            cur = conn.execute("UPDATE bookings SET purpose = ? WHERE id = ?", (purpose, booking_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def delete_and_promote_next(booking: Booking) -> Optional[int]:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            promoted_id = None
            cur.execute("DELETE FROM bookings WHERE id = ?", (booking.id,))

            if booking.status == "confirmed":
                nxt = cur.execute("""
                    SELECT id FROM bookings
                    WHERE room_id = ? AND status = 'queued' AND start_time < ? AND end_time > ?
                    ORDER BY created_at ASC, id ASC
                    LIMIT 1
                """, (booking.room_id, booking.end_time, booking.start_time)).fetchone()

                if nxt:
                    promoted_id = nxt["id"]
                    cur.execute("UPDATE bookings SET status = 'confirmed' WHERE id = ?", (promoted_id,))

            conn.commit()
            return promoted_id
        finally:
            conn.close()