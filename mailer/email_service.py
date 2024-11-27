from flask import Blueprint, jsonify, current_app
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
from database.db_operations import get_contact_and_seller_data
from database.db_operations import save_email_message


logger = logging.getLogger(__name__)
email_blueprint = Blueprint("email", __name__)


def send_email(subject, body, email, contact_id, deal_id):
    """Надсилає електронний лист через SMTP"""
    try:
        logger.info(f"[EMAIL START] Початок відправки email на адресу: {email}")

        smtp_config = current_app.config["SMTP_CONFIG"]
        track_url = f"https://wa.bimedis.net/track_click?email={email}"
        body_with_link = (
            f"{body}\n\nЩоб переглянути більше деталей, натисніть тут: {track_url}"
        )

        msg = MIMEMultipart()
        msg["From"] = smtp_config["FROM"]
        msg["To"] = email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_with_link, "plain"))

        server = smtplib.SMTP(smtp_config["SERVER"], smtp_config["PORT"])
        server.set_debuglevel(1)
        server.starttls()
        server.login(smtp_config["USERNAME"], smtp_config["PASSWORD"])
        server.send_message(msg)
        server.quit()

        # Зберігаємо інформацію про відправлений email
        save_email_message(
            contact_id=contact_id,
            template_name="day1",
            subject=subject,
            body=body_with_link,
            status=1,
            deal_id=deal_id,  # Додаємо deal_id
        )

        logger.info(f"[EMAIL SUCCESS] Лист успішно надіслано на {email}")
        return True
    except Exception as e:
        logger.error(
            f"[EMAIL ERROR] Помилка під час відправлення листа на {email}: {str(e)}"
        )

        # Зберігаємо інформацію про невдалу спробу
        save_email_message(
            contact_id=contact_id,
            template_name="day1",
            subject=subject,
            body=body_with_link,
            status=0,
            deal_id=deal_id,  # Додаємо deal_id
        )

        return False


@email_blueprint.route("/test_email", methods=["GET"])
def test_email():
    """Тестування відправки email"""
    try:
        data = get_contact_and_seller_data()
        if not data or not data["contact"].get("email"):
            return jsonify({"error": "No email found"}), 404

        email_body = (
            f"Hi {data['contact']['name']} {data['contact']['last_name']}\n\n"
            "This is a test email from Bimedis system."
        )

        success = send_email(
            subject="Bimedis Test Email",
            body=email_body,
            email=data["contact"]["email"],
        )

        return jsonify({"success": success, "email": data["contact"]["email"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
