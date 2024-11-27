from flask import Blueprint, request, redirect, jsonify
from database.db_operations import (
    get_contact_by_email,
    save_whatsapp_message,
    save_email_message,
    get_contact_by_phone,
    save_no_contact_reason,
)
from interactive.handlers import (
    handle_days4_yes_response,
    handle_days4_no_response,
    handle_error_message,
)
import logging
import sqlite3
from datetime import datetime
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from flask import current_app

logger = logging.getLogger(__name__)
track_blueprint = Blueprint("tracking", __name__)


def save_click_tracking(email, user_agent, referrer):
    """Зберігає інформацію про клік"""
    try:
        conn = sqlite3.connect("click_tracking.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO click_tracking (email, user_agent, referrer)
            VALUES (?, ?, ?)
        """,
            (email, user_agent, referrer),
        )
        conn.commit()
        conn.close()
        logger.info(f"Успішно збережено клік для {email}")
        return True
    except Exception as e:
        logger.error(f"Помилка збереження кліку: {e}")
        return False


@track_blueprint.route("/track_click", methods=["GET"])
def track_click():
    """Обробка кліків по посиланню та збереження відповідей"""
    try:
        email = request.args.get("email", "unknown")
        response = request.args.get("response")
        template_name = request.args.get("template", "days4")
        referrer = request.headers.get("Referer", "unknown")
        user_agent = request.headers.get("User-Agent", "unknown")

        logger.info(
            f"""
        ===== Click Tracking =====
        Email: {email}
        Template: {template_name}
        Response: {response}
        Referrer: {referrer}
        User Agent: {user_agent}
        Time: {datetime.now()}
        """
        )

        # Зберігаємо дані про клік
        save_click_tracking(email, user_agent, referrer)

        # Отримуємо контакт
        contact = get_contact_by_email(email)
        if not contact:
            logger.error(f"Contact not found for email {email}")
            return redirect("https://bimedis.com")

        # Обробка відповідей на days4
        if template_name == "days4":
            if response and response.lower() == "yes":
                # Відправляємо email з вибором продавця
                from interactive.utils import (
                    get_sellers_for_contact,
                    format_seller_name,
                )

                sellers = get_sellers_for_contact(contact["id"])
                seller_buttons = ""

                for name, last_name in sellers[:3]:  # Максимум 3 продавці
                    button_text = format_seller_name(name, last_name)
                    button_id = f"{name}_{last_name}".replace(" ", "_")
                    seller_buttons += f"""
                        <a href="https://wa.bimedis.net/track_click?response={button_id}&email={email}&template=days4_seller" 
                           class="button">{button_text}</a>
                    """

                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        .button {{
                            display: inline-block;
                            padding: 10px 20px;
                            margin: 10px;
                            background-color: #007bff;
                            color: white;
                            text-decoration: none;
                            border-radius: 5px;
                            font-family: Arial, sans-serif;
                        }}
                    </style>
                </head>
                <body>
                    <div style="text-align: center; padding: 20px;">
                        <p>What seller are you currently in contact with?</p>
                        <div>
                            {seller_buttons}
                        </div>
                    </div>
                </body>
                </html>
                """

                msg = MIMEMultipart()
                msg["From"] = current_app.config["SMTP_CONFIG"]["FROM"]
                msg["To"] = email
                msg["Subject"] = "Select seller - Bimedis"
                msg.attach(MIMEText(html_content, "html"))

                smtp_config = current_app.config["SMTP_CONFIG"]
                server = smtplib.SMTP(smtp_config["SERVER"], smtp_config["PORT"])
                server.starttls()
                server.login(smtp_config["USERNAME"], smtp_config["PASSWORD"])
                server.send_message(msg)
                server.quit()

                save_email_message(
                    contact_id=contact["id"],
                    template_name="days4_seller_selection",
                    subject="Select seller - Bimedis",
                    body=html_content,
                    status=1,
                )

            elif response and response.lower() == "no":
                # Відправляємо email з питанням про причину
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        .button {{
                            display: inline-block;
                            padding: 10px 20px;
                            margin: 10px;
                            background-color: #007bff;
                            color: white;
                            text-decoration: none;
                            border-radius: 5px;
                            font-family: Arial, sans-serif;
                        }}
                    </style>
                </head>
                <body>
                    <div style="text-align: center; padding: 20px;">
                        <p>Why didn't you manage to get in touch with the seller?</p>
                        <div>
                            <a href="https://wa.bimedis.net/track_click?response=seller_not_replying&email={email}&template=days4_reason" 
                               class="button">Seller not replying</a>
                            <a href="https://wa.bimedis.net/track_click?response=no_time_to_contact&email={email}&template=days4_reason" 
                               class="button">No time to contact</a>
                        </div>
                    </div>
                </body>
                </html>
                """

                msg = MIMEMultipart()
                msg["From"] = current_app.config["SMTP_CONFIG"]["FROM"]
                msg["To"] = email
                msg["Subject"] = "Additional feedback required - Bimedis"
                msg.attach(MIMEText(html_content, "html"))

                smtp_config = current_app.config["SMTP_CONFIG"]
                server = smtplib.SMTP(smtp_config["SERVER"], smtp_config["PORT"])
                server.starttls()
                server.login(smtp_config["USERNAME"], smtp_config["PASSWORD"])
                server.send_message(msg)
                server.quit()

                save_email_message(
                    contact_id=contact["id"],
                    template_name="days4_no_reason",
                    subject="Additional feedback required - Bimedis",
                    body=html_content,
                    status=1,
                )

            elif response in ["seller_not_replying", "no_time_to_contact"]:
                save_no_contact_reason(contact["id"], response)
                # Відправляємо підтвердження
                html_content = """
                <!DOCTYPE html>
                <html>
                <body>
                    <div style="text-align: center; padding: 20px;">
                        <p>Thank you for your feedback. Our support team will look into this.</p>
                    </div>
                </body>
                </html>
                """

                msg = MIMEMultipart()
                msg["From"] = current_app.config["SMTP_CONFIG"]["FROM"]
                msg["To"] = email
                msg["Subject"] = "Thank you for your feedback - Bimedis"
                msg.attach(MIMEText(html_content, "html"))

                smtp_config = current_app.config["SMTP_CONFIG"]
                server = smtplib.SMTP(smtp_config["SERVER"], smtp_config["PORT"])
                server.starttls()
                server.login(smtp_config["USERNAME"], smtp_config["PASSWORD"])
                server.send_message(msg)
                server.quit()

                save_email_message(
                    contact_id=contact["id"],
                    template_name="days4_feedback_confirmation",
                    subject="Thank you for your feedback - Bimedis",
                    body=html_content,
                    status=1,
                )

            return redirect("https://bimedis.com/search")

        # За замовчуванням перенаправляємо на головну
        return redirect("https://bimedis.com")

    except Exception as e:
        logger.error(f"Error in track_click: {str(e)}")
        return jsonify({"error": str(e)}), 500


def create_seller_buttons_html(contact_id, email):
    """Створює HTML кнопки для вибору продавця"""
    try:
        from interactive.utils import get_sellers_for_contact, format_seller_name

        sellers = get_sellers_for_contact(contact_id)
        buttons_html = ""

        for name, last_name in sellers[:3]:  # Максимум 3 продавці
            button_text = format_seller_name(name, last_name)
            button_id = f"{name}_{last_name}".replace(" ", "_")
            buttons_html += f"""
                <a href="https://wa.bimedis.net/track_click?response={button_id}&email={email}&template=days4_seller" 
                   class="button">{button_text}</a>
            """

        return buttons_html
    except Exception as e:
        logger.error(f"Error creating seller buttons: {e}")
        return ""


def send_email(email, subject, html_content, template_name, contact_id):
    """Відправляє email та зберігає інформацію в базу"""
    try:
        msg = MIMEMultipart()
        msg["From"] = current_app.config["SMTP_CONFIG"]["FROM"]
        msg["To"] = email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_content, "html"))

        smtp_config = current_app.config["SMTP_CONFIG"]
        server = smtplib.SMTP(smtp_config["SERVER"], smtp_config["PORT"])
        server.starttls()
        server.login(smtp_config["USERNAME"], smtp_config["PASSWORD"])
        server.send_message(msg)
        server.quit()

        save_email_message(
            contact_id=contact_id,
            template_name=template_name,
            subject=subject,
            body=html_content,
            status=1,
        )

        logger.info(f"Email {template_name} sent to {email}")
        return True

    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return False


@track_blueprint.route("/get_click_stats", methods=["GET"])
def get_click_stats():
    """Отримання статистики по кліках"""
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_clicks,
                COUNT(DISTINCT contact_id) as unique_contacts,
                COUNT(DISTINCT email) as unique_emails,
                COUNT(CASE WHEN response IS NOT NULL THEN 1 END) as total_responses,
                COUNT(CASE WHEN response = 'yes' THEN 1 END) as yes_responses,
                COUNT(CASE WHEN response = 'no' THEN 1 END) as no_responses
            FROM click_tracking
            WHERE template_name = 'days4'
        """
        )
        stats = cursor.fetchone()

        # Щоденна статистика
        cursor.execute(
            """
            SELECT 
                strftime('%Y-%m-%d', created_at) as date,
                COUNT(*) as total,
                COUNT(CASE WHEN response = 'yes' THEN 1 END) as yes_responses,
                COUNT(CASE WHEN response = 'no' THEN 1 END) as no_responses
            FROM click_tracking
            WHERE template_name = 'days4'
            GROUP BY date
            ORDER BY date DESC
            LIMIT 30
        """
        )

        daily_stats = []
        for row in cursor.fetchall():
            daily_stats.append(
                {
                    "date": row[0],
                    "total_clicks": row[1],
                    "yes_responses": row[2],
                    "no_responses": row[3],
                }
            )

        conn.close()

        return (
            jsonify(
                {
                    "summary": {
                        "total_clicks": stats[0],
                        "unique_contacts": stats[1],
                        "unique_emails": stats[2],
                        "total_responses": stats[3],
                        "positive_responses": stats[4],
                        "negative_responses": stats[5],
                    },
                    "daily_stats": daily_stats,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Error getting click stats: {str(e)}")
        return jsonify({"error": str(e)}), 500
