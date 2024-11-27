from flask import Blueprint, jsonify, current_app, request
import requests
import time
import logging
from datetime import datetime, timedelta
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from database.db_operations import (
    get_contact_and_seller_data,
    save_whatsapp_message,
    save_email_message,
    get_contact_messages,
)

logger = logging.getLogger(__name__)
sendpulse_blueprint = Blueprint("sendpulse", __name__)


def get_sendpulse_token():
    """Отримання токена доступу від SendPulse"""
    logger.debug("Запит на отримання токена SendPulse")
    url = "https://api.sendpulse.com/oauth/access_token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": current_app.config["SENDPULSE_API_USER_ID"],
        "client_secret": current_app.config["SENDPULSE_API_SECRET"],
    }
    response = requests.post(url, json=payload)
    logger.debug(
        f"Отримано відповідь від SendPulse: {response.status_code} {response.text}"
    )
    response.raise_for_status()
    return response.json().get("access_token")


def check_and_send_follow_up():
    """
    1. Перевіряє day1 повідомлення та надсилає days4 через 5 днів
    2. Перевіряє days4 повідомлення без відповіді та надсилає повторно через 5 днів (до 3 спроб)
    """
    try:
        logger.info("Starting follow-up check process")
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        five_days_ago = datetime.now() - timedelta(days=5)
        five_days_ago_str = five_days_ago.strftime("%Y-%m-%d")

        all_results = []

        # 1. Знаходимо контакти для першого days4 (після day1)
        cursor.execute(
            """
            SELECT 
                m.contact_id, 
                c.phone, 
                c.email,
                c.name, 
                c.last_name, 
                m.created_at, 
                m.status,
                m.message_type
            FROM messages m
            JOIN Contacts c ON m.contact_id = c.id
            WHERE m.template_name = 'day1'
            AND datetime(m.created_at) <= datetime(?)
            AND NOT EXISTS (
                SELECT 1 
                FROM messages m2 
                WHERE m2.contact_id = m.contact_id 
                AND m2.template_name LIKE 'days4%'
            )
        """,
            (five_days_ago_str,),
        )

        new_contacts = cursor.fetchall()

        # 2. Знаходимо days4 повідомлення без відповіді для повторної відправки
        cursor.execute(
            """
            WITH LastDays4 AS (
                -- Отримуємо останнє days4 повідомлення для кожного контакта
                SELECT 
                    contact_id,
                    MAX(created_at) as last_message_date,
                    COUNT(*) as attempts
                FROM messages
                WHERE template_name LIKE 'days4%'
                GROUP BY contact_id
            )
            SELECT 
                m.contact_id,
                c.phone,
                c.email,
                c.name,
                c.last_name,
                m.created_at,
                ld.attempts
            FROM messages m
            JOIN Contacts c ON m.contact_id = c.id
            JOIN LastDays4 ld ON m.contact_id = ld.contact_id
                AND m.created_at = ld.last_message_date
            LEFT JOIN click_tracking ct ON (
                ct.contact_id = m.contact_id 
                AND ct.template_name LIKE 'days4%'
                AND ct.response IS NOT NULL
            )
            WHERE m.template_name LIKE 'days4%'
            AND datetime(m.created_at) <= datetime(?)
            AND ct.id IS NULL  -- Немає відповіді
            AND ld.attempts < 3  -- Менше 3 спроб
            AND NOT EXISTS (
                -- Перевіряємо, чи не було відправлено повідомлення за останні 5 днів
                SELECT 1 FROM messages m2 
                WHERE m2.contact_id = m.contact_id
                AND m2.template_name LIKE 'days4%'
                AND datetime(m2.created_at) > datetime(?)
            )
            GROUP BY m.contact_id
        """,
            (five_days_ago_str, five_days_ago_str),
        )

        retry_contacts = cursor.fetchall()

        logger.info(f"Found {len(new_contacts)} new contacts for first follow-up")
        logger.info(f"Found {len(retry_contacts)} contacts for retry follow-up")

        if new_contacts or retry_contacts:
            token = get_sendpulse_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # Обробляємо нові контакти (перший days4)
            for contact in new_contacts:
                (
                    contact_id,
                    phone,
                    email,
                    name,
                    last_name,
                    created_at,
                    status,
                    message_type,
                ) = contact

                if message_type == "whatsapp" and phone:
                    logger.info(
                        f"Processing WhatsApp follow-up for contact {contact_id}"
                    )
                    # Відправка WhatsApp
                    template_data = {
                        "bot_id": current_app.config["SENDPULSE_WHATSAPP_BOT_ID"],
                        "phone": phone,
                        "template": {"name": "days4", "language": {"code": "en"}},
                    }

                    try:
                        logger.debug(f"Sending WhatsApp template: {template_data}")
                        url = "https://api.sendpulse.com/whatsapp/contacts/sendTemplateByPhone"
                        response = requests.post(
                            url, headers=headers, json=template_data
                        )
                        logger.debug(
                            f"WhatsApp API response: {response.status_code} {response.text}"
                        )

                        if response.status_code == 200:
                            response_data = response.json()
                            if response_data.get("success"):
                                message_details = {
                                    "data": {
                                        "whatsapp_message_id": response_data["data"][
                                            "data"
                                        ]["message_id"],
                                        "sendpulse_message_id": response_data["data"][
                                            "id"
                                        ],
                                        "sendpulse_contact_id": response_data["data"][
                                            "contact_id"
                                        ],
                                        "status": response_data["data"]["status"],
                                    }
                                }

                                save_whatsapp_message(
                                    contact_id=contact_id,
                                    template_name="days4",
                                    message_details=message_details,
                                )

                                all_results.append(
                                    {
                                        "contact_id": contact_id,
                                        "type": "whatsapp_new",
                                        "status": "success",
                                        "response": response_data,
                                    }
                                )
                                logger.info(
                                    f"Successfully sent WhatsApp follow-up to contact {contact_id}"
                                )
                            else:
                                logger.error(
                                    f"SendPulse error response: {response_data}"
                                )
                                all_results.append(
                                    {
                                        "contact_id": contact_id,
                                        "type": "whatsapp_new",
                                        "status": "error",
                                        "error": "SendPulse returned error",
                                    }
                                )
                    except Exception as e:
                        logger.error(
                            f"Error sending WhatsApp to {contact_id}: {str(e)}"
                        )
                        all_results.append(
                            {
                                "contact_id": contact_id,
                                "type": "whatsapp_new",
                                "status": "error",
                                "error": str(e),
                            }
                        )
                elif email:
                    try:
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
                                <p>Hello, did you have a chance to contact the sellers?</p>
                                <div>
                                    <a href="https://wa.bimedis.net/track_click?response=yes&email={email}&template=days4" 
                                       class="button">Yes</a>
                                    <a href="https://wa.bimedis.net/track_click?response=no&email={email}&template=days4" 
                                       class="button">No</a>
                                </div>
                            </div>
                        </body>
                        </html>
                        """

                        msg = MIMEMultipart()
                        msg["From"] = current_app.config["SMTP_CONFIG"]["FROM"]
                        msg["To"] = email
                        msg["Subject"] = "Follow-up on your Bimedis inquiry"
                        msg.attach(MIMEText(html_content, "html"))

                        smtp_config = current_app.config["SMTP_CONFIG"]
                        server = smtplib.SMTP(
                            smtp_config["SERVER"], smtp_config["PORT"]
                        )
                        server.starttls()
                        server.login(smtp_config["USERNAME"], smtp_config["PASSWORD"])
                        server.send_message(msg)
                        server.quit()

                        save_email_message(
                            contact_id=contact_id,
                            template_name="days4",
                            subject="Follow-up on your Bimedis inquiry",
                            body=html_content,
                            status=1,
                        )

                        all_results.append(
                            {
                                "contact_id": contact_id,
                                "type": "email_new",
                                "status": "success",
                            }
                        )

                    except Exception as e:
                        logger.error(f"Error sending email: {e}")
                        all_results.append(
                            {
                                "contact_id": contact_id,
                                "type": "email_new",
                                "status": "error",
                                "error": str(e),
                            }
                        )

            # Обробляємо повторні відправки
            for contact in retry_contacts:
                contact_id, phone, email, name, last_name, created_at, attempts = (
                    contact
                )

                # Перевіряємо, чи не було вже відправлено сьогодні
                cursor.execute(
                    """
                    SELECT created_at 
                    FROM messages 
                    WHERE contact_id = ? 
                    AND template_name LIKE 'days4%'
                    ORDER BY created_at DESC 
                    LIMIT 1
                """,
                    (contact_id,),
                )

                last_message = cursor.fetchone()
                if last_message:
                    last_message_date = datetime.strptime(
                        last_message[0], "%Y-%m-%d %H:%M:%S"
                    )
                    if datetime.now() - last_message_date < timedelta(days=5):
                        logger.info(
                            f"Skipping contact {contact_id} - last message was sent less than 5 days ago"
                        )
                        continue

                # Додаємо attempt_number до повідомлення для відстеження
                template_name = f"days4_retry_{attempts + 1}"

                if attempts < 3:  # Перевіряємо ще раз для певності
                    if phone:
                        logger.info(
                            f"Processing WhatsApp retry for contact {contact_id}"
                        )
                        try:
                            template_data = {
                                "bot_id": current_app.config[
                                    "SENDPULSE_WHATSAPP_BOT_ID"
                                ],
                                "phone": phone,
                                "template": {
                                    "name": "days4",
                                    "language": {"code": "en"},
                                },
                            }

                            logger.debug(
                                f"Sending WhatsApp retry template: {template_data}"
                            )
                            url = "https://api.sendpulse.com/whatsapp/contacts/sendTemplateByPhone"
                            response = requests.post(
                                url, headers=headers, json=template_data
                            )
                            logger.debug(
                                f"WhatsApp API retry response: {response.status_code} {response.text}"
                            )

                            if response.status_code == 200:
                                response_data = response.json()
                                if response_data.get("success"):
                                    message_details = {
                                        "data": {
                                            "whatsapp_message_id": response_data[
                                                "data"
                                            ]["data"]["message_id"],
                                            "sendpulse_message_id": response_data[
                                                "data"
                                            ]["id"],
                                            "sendpulse_contact_id": response_data[
                                                "data"
                                            ]["contact_id"],
                                            "status": response_data["data"]["status"],
                                        }
                                    }

                                    save_whatsapp_message(
                                        contact_id=contact_id,
                                        template_name=template_name,
                                        message_details=message_details,
                                    )

                                    all_results.append(
                                        {
                                            "contact_id": contact_id,
                                            "type": "whatsapp_retry",
                                            "attempt": attempts + 1,
                                            "status": "success",
                                            "response": response_data,
                                        }
                                    )
                                    logger.info(
                                        f"Successfully sent WhatsApp retry to contact {contact_id}"
                                    )
                                else:
                                    logger.error(
                                        f"SendPulse error response for retry: {response_data}"
                                    )
                                    all_results.append(
                                        {
                                            "contact_id": contact_id,
                                            "type": "whatsapp_retry",
                                            "attempt": attempts + 1,
                                            "status": "error",
                                            "error": "SendPulse returned error",
                                        }
                                    )
                        except Exception as e:
                            logger.error(
                                f"Error sending WhatsApp retry to {contact_id}: {str(e)}"
                            )
                            all_results.append(
                                {
                                    "contact_id": contact_id,
                                    "type": "whatsapp_retry",
                                    "attempt": attempts + 1,
                                    "status": "error",
                                    "error": str(e),
                                }
                            )
                    # ... попередній код

                    elif email:
                        try:
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
                                    <p>Hello, we noticed you haven't responded to our previous message. 
                                       Did you have a chance to contact the sellers?</p>
                                    <div>
                                        <a href="https://wa.bimedis.net/track_click?response=yes&email={email}&template={template_name}" 
                                           class="button">Yes</a>
                                        <a href="https://wa.bimedis.net/track_click?response=no&email={email}&template={template_name}" 
                                           class="button">No</a>
                                    </div>
                                </div>
                            </body>
                            </html>
                            """

                            msg = MIMEMultipart()
                            msg["From"] = current_app.config["SMTP_CONFIG"]["FROM"]
                            msg["To"] = email
                            msg["Subject"] = "Follow-up on your Bimedis inquiry"
                            msg.attach(MIMEText(html_content, "html"))

                            smtp_config = current_app.config["SMTP_CONFIG"]
                            server = smtplib.SMTP(
                                smtp_config["SERVER"], smtp_config["PORT"]
                            )
                            server.starttls()
                            server.login(
                                smtp_config["USERNAME"], smtp_config["PASSWORD"]
                            )
                            server.send_message(msg)
                            server.quit()

                            save_email_message(
                                contact_id=contact_id,
                                template_name=template_name,
                                subject="Follow-up on your Bimedis inquiry",
                                body=html_content,
                                status=1,
                            )

                            all_results.append(
                                {
                                    "contact_id": contact_id,
                                    "type": "email_retry",
                                    "attempt": attempts + 1,
                                    "status": "success",
                                }
                            )

                        except Exception as e:
                            logger.error(f"Error sending retry email: {e}")
                            all_results.append(
                                {
                                    "contact_id": contact_id,
                                    "type": "email_retry",
                                    "attempt": attempts + 1,
                                    "status": "error",
                                    "error": str(e),
                                }
                            )

        conn.close()
        logger.info("Follow-up process completed")
        return all_results

    except Exception as e:
        logger.error(f"Error in follow-up processing: {str(e)}")
        if "conn" in locals():
            conn.close()
        return {"error": str(e)}


@sendpulse_blueprint.route("/send_follow_up", methods=["POST"])
def send_follow_up():
    """Ендпоінт для відправки follow-up повідомлень"""
    try:
        results = check_and_send_follow_up()
        return jsonify({"status": "success", "results": results}), 200
    except Exception as e:
        logger.error(f"Error in follow-up endpoint: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@sendpulse_blueprint.route("/get_contact_messages/<int:contact_id>", methods=["GET"])
def contact_messages(contact_id):
    """Отримання всіх повідомлень для конкретного контакта"""
    try:
        messages = get_contact_messages(contact_id)
        return (
            jsonify(
                {"status": "success", "contact_id": contact_id, "messages": messages}
            ),
            200,
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@sendpulse_blueprint.route("/check_message_status/<contact_id>", methods=["GET"])
def check_message_status(contact_id):
    """Перевірка статусу надісланого повідомлення"""
    try:
        token = get_sendpulse_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        url = f"https://api.sendpulse.com/whatsapp/chats/messages?contact_id={contact_id}&size=1&order=desc"
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            messages = response.json().get("data", [])
            if messages:
                last_message = messages[0]
                status = last_message.get("status")

                return (
                    jsonify(
                        {
                            "status": "success",
                            "message_status": status,
                            "message_details": last_message,
                        }
                    ),
                    200,
                )
            else:
                return jsonify({"error": "No messages found"}), 404
        else:
            return (
                jsonify({"error": "Failed to check message status"}),
                response.status_code,
            )

    except Exception as e:
        logger.exception("Помилка перевірки статусу повідомлення")
        return jsonify({"error": str(e)}), 500


@sendpulse_blueprint.route("/check_template_format", methods=["GET"])
def check_template_format():
    """Перевірка форматування даних для шаблону"""
    try:
        data = get_contact_and_seller_data()
        if not data:
            return jsonify({"error": "No data found"}), 404

        contact_full_name = (
            f"{data['contact']['name']} {data['contact']['last_name']}".strip()
        )
        seller_info = (
            f"\\n👤: {data['seller']['name']} {data['seller']['last_name']},\\n"
            f"📞: {data['seller']['phone']}, \\n"
            f"✉️: {data['seller']['email']}\\n\\n"
        ).strip()

        return jsonify(
            {
                "contact_name": contact_full_name,
                "seller_info": seller_info,
                "phone": data["contact"]["phone"],
                "email": data["contact"]["email"],
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sendpulse_blueprint.route("/send_template_message", methods=["POST"])
def send_template_message():
    """Надсилання шаблонного повідомлення з даними з бази та перевірка статусу"""
    try:
        data = get_contact_and_seller_data()
        if not data:
            logger.error("Дані контакта не знайдено в базі")
            return jsonify({"error": "Contact data not found"}), 404

        contact_full_name = (
            f"{data['contact']['name']} {data['contact']['last_name']}".strip()
        )
        seller_info = (
            f"\\n👤: {data['seller']['name']} {data['seller']['last_name']},\\n"
            f"📞: {data['seller']['phone']}, \\n"
            f"✉️: {data['seller']['email']}\\n\\n"
        ).strip()

        token = get_sendpulse_token()
        if not token:
            logger.error("Failed to get SendPulse token")
            return False

        if data["contact"].get("phone"):
            # Спроба відправити WhatsApp
            payload = {
                "bot_id": current_app.config["SENDPULSE_WHATSAPP_BOT_ID"],
                "phone": data["contact"]["phone"],
                "template": {
                    "name": "day1",
                    "language": {"code": "en"},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": contact_full_name},
                                {"type": "text", "text": seller_info},
                            ],
                        }
                    ],
                },
            }

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                "https://api.sendpulse.com/whatsapp/contacts/sendTemplateByPhone",
                headers=headers,
                json=payload,
            )

            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("success"):
                    message_details = response_data.get("data", {})
                    contact_id = message_details.get("contact_id")

                    if contact_id:
                        time.sleep(3)  # Чекаємо щоб отримати актуальний статус
                        status_response = requests.get(
                            f"https://api.sendpulse.com/whatsapp/chats/messages?contact_id={contact_id}&size=1&order=desc",
                            headers=headers,
                        )

                        if status_response.status_code == 200:
                            messages = status_response.json().get("data", [])
                            if messages:
                                last_message = messages[0]
                                status = last_message.get("status")

                                if status == 6 and data["contact"].get("email"):
                                    # Якщо WhatsApp не вдався і є email, відправляємо email
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
                                            <p>Hi {contact_full_name}</p>
                                            <p>It is the customer assistance department of Bimedis. 
                                            Lately you were interested in buying multiple products.</p>
                                            <p>Here is the seller's contact information:</p>
                                            <p>{seller_info}</p>
                                            <p>Please let me know if you were able to contact the seller:</p>
                                            <div>
                                                <a href="https://wa.bimedis.net/track_click?response=yes&email={data['contact']['email']}&template=day1" 
                                                   class="button">Yes</a>
                                                <a href="https://wa.bimedis.net/track_click?response=no&email={data['contact']['email']}&template=day1" 
                                                   class="button">No</a>
                                            </div>
                                        </div>
                                    </body>
                                    </html>
                                    """

                                    msg = MIMEMultipart()
                                    msg["From"] = current_app.config["SMTP_CONFIG"][
                                        "FROM"
                                    ]
                                    msg["To"] = data["contact"]["email"]
                                    msg["Subject"] = "Follow-up on your Bimedis inquiry"
                                    msg.attach(MIMEText(html_content, "html"))

                                    smtp_config = current_app.config["SMTP_CONFIG"]
                                    server = smtplib.SMTP(
                                        smtp_config["SERVER"], smtp_config["PORT"]
                                    )
                                    server.starttls()
                                    server.login(
                                        smtp_config["USERNAME"], smtp_config["PASSWORD"]
                                    )
                                    server.send_message(msg)
                                    server.quit()

                                    save_email_message(
                                        contact_id=data["contact"]["id"],
                                        template_name="day1",
                                        subject="Follow-up on your Bimedis inquiry",
                                        body=html_content,
                                        status=1,
                                    )
                                else:
                                    # Зберігаємо інформацію про WhatsApp
                                    save_whatsapp_message(
                                        contact_id=data["contact"]["id"],
                                        template_name="day1",
                                        message_details=last_message,
                                    )

                return (
                    jsonify(
                        {
                            "status": "success",
                            "message_sent": True,
                            "response": response_data,
                        }
                    ),
                    200,
                )

        # Якщо немає телефону або WhatsApp не вдався, відправляємо email
        elif data["contact"].get("email"):
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
                    <p>Hi {contact_full_name}</p>
                    <p>It is the customer assistance department of Bimedis. 
                    Lately you were interested in buying multiple products.</p>
                    <p>Here is the seller's contact information:</p>
                    <p>{seller_info}</p>
                    <p>Please let me know if you were able to contact the seller:</p>
                    <div>
                        <a href="https://wa.bimedis.net/track_click?response=yes&email={data['contact']['email']}&template=day1" 
                           class="button">Yes</a>
                        <a href="https://wa.bimedis.net/track_click?response=no&email={data['contact']['email']}&template=day1" 
                           class="button">No</a>
                    </div>
                </div>
            </body>
            </html>
            """

            msg = MIMEMultipart()
            msg["From"] = current_app.config["SMTP_CONFIG"]["FROM"]
            msg["To"] = data["contact"]["email"]
            msg["Subject"] = "Follow-up on your Bimedis inquiry"
            msg.attach(MIMEText(html_content, "html"))

            smtp_config = current_app.config["SMTP_CONFIG"]
            server = smtplib.SMTP(smtp_config["SERVER"], smtp_config["PORT"])
            server.starttls()
            server.login(smtp_config["USERNAME"], smtp_config["PASSWORD"])
            server.send_message(msg)
            server.quit()

            save_email_message(
                contact_id=data["contact"]["id"],
                template_name="day1",
                subject="Follow-up on your Bimedis inquiry",
                body=html_content,
                status=1,
            )

            return jsonify({"status": "success", "message": "Email sent"}), 200

        return jsonify({"error": "No contact methods available"}), 400

    except Exception as e:
        error_message = f"Помилка відправки повідомлення: {str(e)}"
        logger.exception(error_message)
        return jsonify({"error": error_message}), 500
