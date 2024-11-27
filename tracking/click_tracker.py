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
import requests
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


def send_whatsapp_confirmation(phone, message_text):
    """Відправляє підтверджувальне повідомлення через WhatsApp"""
    try:
        token = get_sendpulse_token()
        if not token:
            logger.error("Failed to get SendPulse token")
            return False

        payload = {
            "bot_id": current_app.config["SENDPULSE_WHATSAPP_BOT_ID"],
            "phone": phone,
            "message": {"type": "text", "text": message_text},
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            "https://api.sendpulse.com/whatsapp/contacts/send",
            headers=headers,
            json=payload,
        )

        return response.status_code == 200

    except Exception as e:
        logger.error(f"Error sending WhatsApp confirmation: {e}")
        return False


def send_email_confirmation(email, message_text):
    """Відправляє підтверджувальне повідомлення через email"""
    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body>
            <div style="text-align: center; padding: 20px;">
                <p>{message_text}</p>
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

        return True

    except Exception as e:
        logger.error(f"Error sending email confirmation: {e}")
        return False


def handle_communication_response(contact_id, response_type, phone=None, email=None):
    """Обробляє відповідь про статус комунікації з продавцем"""
    try:
        response_text = (
            "Everything is fine"
            if response_type == "communication_ok"
            else "No reply from seller"
        )

        # Зберігаємо відповідь
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO message_responses (
                contact_id,
                template_name,
                response_text,
                additional_data
            ) VALUES (?, ?, ?, ?)
        """,
            (
                contact_id,
                "seller_communication",
                response_type,
                json.dumps(
                    {
                        "response_text": response_text,
                        "timestamp": datetime.now().isoformat(),
                    }
                ),
            ),
        )

        conn.commit()
        conn.close()

        # Відправляємо підтвердження отримання відповіді
        confirmation_text = "Thank you for your feedback! " + (
            "We'll make sure to follow up with the seller."
            if response_type == "no_reply"
            else "We're glad to hear that!"
        )

        if phone:
            send_whatsapp_confirmation(phone, confirmation_text)
        if email:
            send_email_confirmation(email, confirmation_text)

        return True

    except Exception as e:
        logger.error(f"Error handling communication response: {e}")
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

        # Обробка відповідей на seller_communication
        if template_name == "seller_communication":
            if response in ["communication_ok", "no_reply"]:
                handle_communication_response(
                    contact_id=contact["id"], response_type=response, email=email
                )
            return redirect("https://bimedis.com")

        # Обробка відповіді з вибором продавця
        if template_name == "days4_seller":
            if "_" in response:  # Це відповідь з вибором продавця
                # Відправляємо питання про комунікацію
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
                        <p>How your communication with the seller is going?</p>
                        <div>
                            <a href="https://wa.bimedis.net/track_click?response=communication_ok&email={email}&template=seller_communication" 
                               class="button">Everything is fine</a>
                            <a href="https://wa.bimedis.net/track_click?response=no_reply&email={email}&template=seller_communication" 
                               class="button">No reply from seller</a>
                        </div>
                    </div>
                </body>
                </html>
                """

                msg = MIMEMultipart()
                msg["From"] = current_app.config["SMTP_CONFIG"]["FROM"]
                msg["To"] = email
                msg["Subject"] = "Communication Status - Bimedis"
                msg.attach(MIMEText(html_content, "html"))

                smtp_config = current_app.config["SMTP_CONFIG"]
                server = smtplib.SMTP(smtp_config["SERVER"], smtp_config["PORT"])
                server.starttls()
                server.login(smtp_config["USERNAME"], smtp_config["PASSWORD"])
                server.send_message(msg)
                server.quit()

                save_email_message(
                    contact_id=contact["id"],
                    template_name="seller_communication_check",
                    subject="Communication Status - Bimedis",
                    body=html_content,
                    status=1,
                )

                # Якщо є телефон - також відправляємо WhatsApp
                if contact.get("phone"):
                    token = get_sendpulse_token()
                    if token:
                        buttons = [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "communication_ok",
                                    "title": "Everything is fine",
                                },
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "no_reply",
                                    "title": "No reply from seller",
                                },
                            },
                        ]

                        payload = {
                            "bot_id": current_app.config["SENDPULSE_WHATSAPP_BOT_ID"],
                            "phone": contact["phone"],
                            "message": {
                                "type": "interactive",
                                "interactive": {
                                    "type": "button",
                                    "body": {
                                        "text": "How your communication with the seller is going?"
                                    },
                                    "action": {"buttons": buttons},
                                },
                            },
                        }

                        headers = {
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        }

                        url = "https://api.sendpulse.com/whatsapp/contacts/send"
                        response = requests.post(url, headers=headers, json=payload)

                        if response.status_code == 200:
                            response_data = response.json()
                            if response_data.get("success"):
                                message_details = {
                                    "data": {
                                        "whatsapp_message_id": response_data["data"][
                                            "data"
                                        ].get("message_id"),
                                        "sendpulse_message_id": response_data[
                                            "data"
                                        ].get("id"),
                                        "sendpulse_contact_id": str(contact["id"]),
                                        "status": response_data["data"].get(
                                            "status", 1
                                        ),
                                    }
                                }

                                save_whatsapp_message(
                                    contact_id=contact["id"],
                                    template_name="seller_communication_check",
                                    message_details=message_details,
                                )

                # Зберігаємо вибір продавця
                seller_name, seller_last_name = response.split("_")
                seller_data = {"name": seller_name, "last_name": seller_last_name}
                save_seller_choice(contact["id"], seller_data)

            return redirect("https://bimedis.com/search")

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


def handle_button_response(button_id, phone):
    """Обробляє відповідь на кнопку вибору продавця"""
    try:
        logger.info(f"Processing button response: {button_id} from {phone}")

        # Отримуємо дані контакта
        contact = get_contact_by_phone(phone)
        if not contact:
            logger.error(f"Contact not found for phone {phone}")
            return False

        # Розбираємо ID кнопки для отримання даних продавця
        seller_data = get_seller_info_from_button(button_id)
        if not seller_data:
            logger.error(f"Could not parse seller info from button_id: {button_id}")
            return False

        token = get_sendpulse_token()
        if not token:
            logger.error("Failed to get SendPulse token")
            return False

        # Створюємо повідомлення з питанням про комунікацію
        if contact.get("phone"):  # Якщо є телефон - відправляємо WhatsApp
            buttons = [
                {
                    "type": "reply",
                    "reply": {"id": "communication_ok", "title": "Everything is fine"},
                },
                {
                    "type": "reply",
                    "reply": {"id": "no_reply", "title": "No reply from seller"},
                },
            ]

            payload = {
                "bot_id": current_app.config["SENDPULSE_WHATSAPP_BOT_ID"],
                "phone": phone,
                "message": {
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {
                            "text": "How your communication with the seller is going?"
                        },
                        "action": {"buttons": buttons},
                    },
                },
            }

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            url = "https://api.sendpulse.com/whatsapp/contacts/send"
            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("success"):
                    message_details = {
                        "data": {
                            "whatsapp_message_id": response_data["data"]["data"].get(
                                "message_id"
                            ),
                            "sendpulse_message_id": response_data["data"].get("id"),
                            "sendpulse_contact_id": str(contact["id"]),
                            "status": response_data["data"].get("status", 1),
                        }
                    }

                    save_whatsapp_message(
                        contact_id=contact["id"],
                        template_name="seller_communication_check",
                        message_details=message_details,
                    )

        if contact.get("email"):  # Якщо є email - відправляємо email
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
                    <p>How your communication with the seller is going?</p>
                    <div>
                        <a href="https://wa.bimedis.net/track_click?response=communication_ok&email={contact['email']}&template=seller_communication" 
                           class="button">Everything is fine</a>
                        <a href="https://wa.bimedis.net/track_click?response=no_reply&email={contact['email']}&template=seller_communication" 
                           class="button">No reply from seller</a>
                    </div>
                </div>
            </body>
            </html>
            """

            msg = MIMEMultipart()
            msg["From"] = current_app.config["SMTP_CONFIG"]["FROM"]
            msg["To"] = contact["email"]
            msg["Subject"] = "Seller Communication Status - Bimedis"
            msg.attach(MIMEText(html_content, "html"))

            smtp_config = current_app.config["SMTP_CONFIG"]
            server = smtplib.SMTP(smtp_config["SERVER"], smtp_config["PORT"])
            server.starttls()
            server.login(smtp_config["USERNAME"], smtp_config["PASSWORD"])
            server.send_message(msg)
            server.quit()

            save_email_message(
                contact_id=contact["id"],
                template_name="seller_communication_check",
                subject="Seller Communication Status - Bimedis",
                body=html_content,
                status=1,
            )

        # Зберігаємо вибір продавця
        save_seller_choice(contact["id"], seller_data)
        logger.info(
            f"Successfully sent communication check messages for contact {contact['id']}"
        )
        return True

    except Exception as e:
        logger.error(f"Error handling button response: {e}", exc_info=True)
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
