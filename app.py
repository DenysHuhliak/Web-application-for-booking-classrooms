from flask import Flask, jsonify, render_template, request
from validators import ApiError
from repositories import RoomRepository, BookingRepository
from services import AuthService, RoomService, BookingService
from auth import require_roles, get_Authenticated_user
from datetime import date

app = Flask(__name__)

@app.errorhandler(ApiError)
def handle_api_error(error: ApiError):
    return jsonify({"status": error.status, "error": error.message, "message": error.message}), error.status

@app.errorhandler(404)
def handle_not_found(_):
    return jsonify({"status": 404, "message": "Запитуваний ресурс або маршрут не знайдено."}), 404

@app.errorhandler(500)
def handle_internal_error(_):
    return jsonify({"status": 500, "message": "Внутрішня помилка сервера."}), 500

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/auth/login", methods=["POST"])
def login():
    result = AuthService.login_user(request.get_json(silent=True) or {})
    return jsonify(result), 200

@app.route("/api/auth/register", methods=["POST"])
def register():
    result = AuthService.register_user(request.get_json(silent=True) or {})
    return jsonify(result), 201

@app.route("/api/rooms", methods=["GET"])
def get_rooms():
    current_user = get_Authenticated_user() if request.headers.get("Authorization") else None

    rooms = RoomService.get_rooms_with_occupancy(
        date_str=request.args.get("date", date.today().isoformat()),
        time_slot=request.args.get("slot", "09:00-10:20"),
        min_capacity=request.args.get("capacity", 0, type=int),
        equipment=request.args.get("equipment", ""),
        current_user=current_user
    )
    return jsonify(rooms), 200

@app.route("/api/rooms/<int:room_id>", methods=["GET"])
def get_room_by_id(room_id: int):
    room = RoomRepository.get_by_id(room_id)
    if not room:
        raise ApiError(404, f"Аудиторію з id={room_id} не знайдено.")
    return jsonify(room.to_dict()), 200

@app.route("/api/rooms/<int:room_id>/status", methods=["PATCH"])
@require_roles("admin")
def update_room_status(room_id: int):
    data = request.get_json(silent=True) or {}
    if "is_active" not in data:
        raise ApiError(400, "Необхідно передати поле is_active (0 або 1).")
    updated = RoomService.set_room_active_state(room_id, int(data["is_active"]))
    return jsonify({"status": 200, "message": "Статус активності аудиторії оновлено.", "room": updated}), 200

@app.route("/api/bookings", methods=["GET"])
@require_roles("admin", "teacher")
def get_bookings():
    return jsonify(BookingService.list_bookings(request.current_user)), 200

@app.route("/api/bookings/<int:booking_id>", methods=["GET"])
def get_booking_by_id(booking_id: int):
    booking = BookingRepository.get_by_id(booking_id)
    if not booking:
        raise ApiError(404, f"Бронювання з id={booking_id} не знайдено.")
    return jsonify(booking.to_dict()), 200

@app.route("/api/bookings", methods=["POST"])
@require_roles("admin", "teacher")
def create_booking():
    result = BookingService.create_booking_or_queue(request.get_json(silent=True), request.current_user)
    return jsonify(result), 201

@app.route("/api/bookings/<int:booking_id>", methods=["PATCH"])
@require_roles("admin", "teacher")
def update_booking(booking_id: int):
    data = request.get_json(silent=True) or {}
    updated = BookingService.update_booking_purpose(booking_id, data.get("purpose"), request.current_user)
    return jsonify({"status": 200, "message": "Призначення бронювання успішно оновлено.", "booking": updated}), 200

@app.route("/api/bookings/<int:booking_id>", methods=["DELETE"])
@require_roles("admin", "teacher")
def delete_booking(booking_id: int):
    return jsonify(BookingService.cancel_booking(booking_id, request.current_user)), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)