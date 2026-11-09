import os
import sys
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from dotenv import load_dotenv
from models import Booking

load_dotenv(override=True)


class EmailNotificationService:
    sent_outbox = []

    @classmethod
    def _send_email(cls, recipient: str, subject: str, body: str) -> bool:
        if not recipient:
            return False

        load_dotenv(override=True)
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
        smtp_port = int(os.getenv("SMTP_PORT", "587").strip())
        smtp_user = os.getenv("SMTP_USER", "").strip()
        smtp_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "").strip()
        sender_email = os.getenv("SMTP_SENDER", smtp_user or "noreply-booking@pnu.edu.ua").strip()

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr(("Система бронювання ПНУ", sender_email))
        msg["To"] = recipient
        msg.set_content(body, charset="utf-8")

        cls.sent_outbox.append({
            "to": recipient,
            "subject": subject,
            "body": body
        })

        is_testing = "pytest" in sys.modules or os.getenv("FLASK_TESTING") == "1"

        if smtp_user and smtp_password and not is_testing:
            try:
                if smtp_port == 465:
                    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as server:
                        server.login(smtp_user, smtp_password)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                        server.ehlo()
                        server.starttls()
                        server.ehlo()
                        server.login(smtp_user, smtp_password)
                        server.send_message(msg)

                print(f"[SMTP SUCCESS] Лист успішно надіслано на пошту: {recipient}")
                return True
            except Exception as exc:
                print(f"[SMTP ERROR] Не вдалося надіслати лист на {recipient}: {exc}")
                return False

        print(
            f"\n[EMAIL LOG] Кому: {recipient} | Тема: {subject}\n"
            f"Текст: {body.strip()}\n"
        )
        return True

    @classmethod
    def send_booking_created(cls, booking: Booking) -> bool:
        if booking.status == "confirmed":
            subject = f"Підтверджено бронювання аудиторії №{booking.room_number}"
            body = (
                f"Вітаємо, {booking.teacher_name}!\n\n"
                f"Ваше бронювання аудиторії №{booking.room_number} успішно підтверджено.\n"
                f"Призначення: {booking.purpose}\n"
                f"Час заняття: {booking.start_time} – {booking.end_time}\n"
                f"Статус: Підтверджено (confirmed)."
            )
        else:
            subject = f"Заявку на аудиторію №{booking.room_number} додано в чергу очікування"
            body = (
                f"Вітаємо, {booking.teacher_name}!\n\n"
                f"Аудиторія №{booking.room_number} наразі зайнята на обраний час.\n"
                f"Вашу заявку ({booking.purpose}) додано до черги очікування.\n"
                f"Час заняття: {booking.start_time} – {booking.end_time}\n"
                f"Статус: В черзі (queued). Ми повідомимо вас, якщо аудиторія звільниться."
            )
        return cls._send_email(booking.email, subject, body)

    @classmethod
    def send_queue_promoted(cls, booking: Booking) -> bool:
        subject = f"Аудиторія №{booking.room_number} звільнилася — ваше бронювання підтверджено!"
        body = (
            f"Вітаємо, {booking.teacher_name}!\n\n"
            f"Попереднє бронювання було скасовано, тому вашу заявку з черги очікування "
            f"автоматично переведено у статус підтвердженої (confirmed).\n"
            f"Аудиторія: №{booking.room_number}\n"
            f"Призначення: {booking.purpose}\n"
            f"Час заняття: {booking.start_time} – {booking.end_time}"
        )
        return cls._send_email(booking.email, subject, body)

    @classmethod
    def send_booking_cancelled(
        cls,
        booking: Booking,
        cancelled_by_admin: bool = False,
        admin_name: str = ""
    ) -> bool:
        if cancelled_by_admin:
            admin_info = f" ({admin_name})" if admin_name else ""
            subject = f"Адміністратор скасував ваше бронювання аудиторії №{booking.room_number}"
            body = (
                f"Вітаємо, {booking.teacher_name}!\n\n"
                f"Повідомляємо, що адміністратор системи{admin_info} скасував ваше бронювання "
                f"аудиторії №{booking.room_number} ({booking.purpose}) "
                f"на час {booking.start_time} – {booking.end_time}.\n"
                f"Якщо у вас виникли запитання, зверніться до диспетчера розкладу."
            )
        else:
            subject = f"Скасовано бронювання аудиторії №{booking.room_number}"
            body = (
                f"Вітаємо, {booking.teacher_name}!\n\n"
                f"Ви успішно скасували власне бронювання аудиторії №{booking.room_number} "
                f"({booking.purpose}) на час {booking.start_time} – {booking.end_time}."
            )
        return cls._send_email(booking.email, subject, body)