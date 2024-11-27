import sqlite3
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)


def get_contact_and_seller_data():
    """Отримує дані контакта та його продавця з бази"""
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 
                c.id, c.name, c.last_name, c.phone, c.email,
                ds.name as seller_name, ds.last_name as seller_last_name,
                ds.email as seller_email, ds.phone as seller_phone
            FROM Contacts c
            JOIN Deals d ON c.id = d.contact_id
            JOIN DealSellers ds ON d.id = ds.deal_id
            WHERE c.id = 165553
            LIMIT 1
        """
        )

        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                "contact": {
                    "id": result[0],
                    "name": result[1],
                    "last_name": result[2],
                    "phone": result[3],
                    "email": result[4],
                },
                "seller": {
                    "name": result[5],
                    "last_name": result[6],
                    "email": result[7],
                    "phone": result[8],
                },
            }
        return None
    except Exception as e:
        logger.error(f"Помилка отримання даних з бази: {e}")
        return None


def get_contact_by_email(email):
    """Отримує дані контакта за email"""
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 
                id,
                name,
                last_name,
                phone,
                email
            FROM Contacts 
            WHERE email = ?
            LIMIT 1
        """,
            (email,),
        )

        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                "id": result[0],
                "name": result[1],
                "last_name": result[2],
                "phone": result[3],
                "email": result[4],
            }
        return None
    except Exception as e:
        logger.error(f"Error getting contact by email {email}: {e}")
        return None


def get_contact_by_phone(phone):
    """Отримує дані контакта за номером телефону"""
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        # Нормалізуємо номер телефону для пошуку
        normalized_phone = phone.replace("+", "").strip()

        cursor.execute(
            """
            SELECT 
                id,
                name,
                last_name,
                phone,
                email
            FROM Contacts 
            WHERE REPLACE(REPLACE(phone, '+', ''), ' ', '') = ?
            LIMIT 1
        """,
            (normalized_phone,),
        )

        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                "id": result[0],
                "name": result[1],
                "last_name": result[2],
                "phone": result[3],
                "email": result[4],
            }
        return None
    except Exception as e:
        logger.error(f"Error getting contact by phone {phone}: {e}")
        return None


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


def save_whatsapp_message(contact_id, template_name, message_details):
    """Зберігає інформацію про WhatsApp повідомлення"""
    try:
        logger.info(
            f"""
        ====== Saving WhatsApp Message ======
        Contact ID: {contact_id}
        Template: {template_name}
        Message Details: {message_details}
        """
        )

        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        data = message_details.get("data", {})
        whatsapp_message_id = data.get("whatsapp_message_id")
        sendpulse_message_id = data.get("sendpulse_message_id")
        sendpulse_contact_id = data.get("sendpulse_contact_id")
        status = data.get("status", 3)

        logger.info(
            f"""
        Extracted values:
        whatsapp_message_id: {whatsapp_message_id}
        sendpulse_message_id: {sendpulse_message_id}
        sendpulse_contact_id: {sendpulse_contact_id}
        status: {status}
        """
        )

        cursor.execute(
            """
            INSERT INTO messages (
                contact_id,
                message_type,
                template_name,
                whatsapp_message_id,
                sendpulse_message_id,
                sendpulse_contact_id,
                status,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
            (
                contact_id,
                "whatsapp",
                template_name,
                whatsapp_message_id,
                sendpulse_message_id,
                sendpulse_contact_id,
                status,
            ),
        )

        # Перевіряємо, чи дійсно дані збереглися
        cursor.execute(
            """
            SELECT * FROM messages 
            WHERE contact_id = ? 
            AND template_name = ? 
            ORDER BY created_at DESC 
            LIMIT 1
        """,
            (contact_id, template_name),
        )

        saved_data = cursor.fetchone()
        logger.info(f"Saved data in database: {saved_data}")

        conn.commit()
        conn.close()

        logger.info(
            f"WhatsApp повідомлення успішно збережено для контакта {contact_id}"
        )
        return True

    except sqlite3.Error as sql_error:
        logger.error(f"SQLite error: {sql_error}")
        if "conn" in locals():
            conn.close()
        return False
    except Exception as e:
        logger.error(f"Unexpected error in save_whatsapp_message: {str(e)}")
        if "conn" in locals():
            conn.close()
        return False


def save_email_message(
    contact_id, template_name, subject, body, status=1, deal_id=None
):
    """Зберігає інформацію про відправлений email"""
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO messages (
                contact_id,
                deal_id,
                message_type,
                template_name,
                message_text,
                status
            ) VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                contact_id,
                deal_id,
                "email",
                template_name,
                f"Subject: {subject}\n\nBody: {body}",
                status,
            ),
        )

        conn.commit()
        conn.close()
        logger.info(f"Email повідомлення збережено для контакта {contact_id}")
        return True
    except Exception as e:
        logger.error(f"Помилка збереження email повідомлення: {e}")
        return False


def get_contact_messages(contact_id):
    """Отримує всі повідомлення для конкретного контакта"""
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 
                message_type,
                template_name,
                message_text,
                whatsapp_message_id,
                sendpulse_message_id,
                status,
                created_at
            FROM messages
            WHERE contact_id = ?
            ORDER BY created_at DESC
        """,
            (contact_id,),
        )

        messages = cursor.fetchall()
        conn.close()

        return [
            {
                "message_type": msg[0],
                "template_name": msg[1],
                "message_text": msg[2],
                "whatsapp_message_id": msg[3],
                "sendpulse_message_id": msg[4],
                "status": msg[5],
                "created_at": msg[6],
            }
            for msg in messages
        ]
    except Exception as e:
        logger.error(f"Помилка отримання повідомлень: {e}")
        return []


def save_seller_choice(contact_id, seller_data):
    """Зберігає вибір продавця"""
    try:
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
                "seller_selected",
                f"{seller_data['name']} {seller_data['last_name']}",
                json.dumps(
                    {
                        "seller_name": seller_data["name"],
                        "seller_last_name": seller_data["last_name"],
                        "timestamp": datetime.now().isoformat(),
                    }
                ),
            ),
        )

        conn.commit()
        conn.close()

        logger.info(
            f"Saved seller choice for contact {contact_id}: {seller_data['name']} {seller_data['last_name']}"
        )
        return True

    except Exception as e:
        logger.error(f"Error saving seller choice: {e}")
        if "conn" in locals():
            conn.close()
        return False


def get_seller_responses_stats():
    """Отримує статистику відповідей по продавцям"""
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 
                json_extract(additional_data, '$.seller_id') as seller_id,
                COUNT(*) as total_responses,
                SUM(CASE WHEN response_text = 'selected' THEN 1 ELSE 0 END) as positive_responses,
                AVG(CASE WHEN response_text = 'selected' THEN 1 ELSE 0 END) * 100 as response_rate
            FROM message_responses
            WHERE template_name = 'seller_selection'
            AND additional_data IS NOT NULL
            GROUP BY seller_id
        """
        )

        stats = cursor.fetchall()
        conn.close()

        return [
            {
                "seller_id": stat[0],
                "total_responses": stat[1],
                "positive_responses": stat[2],
                "response_rate": round(stat[3], 2),
            }
            for stat in stats
        ]
    except Exception as e:
        logger.error(f"Error getting seller responses stats: {e}")
        return []


def save_no_contact_reason(contact_id, reason):
    """Зберігає причину відсутності контакту з продавцем"""
    try:
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
                "days4_no_contact_reason",
                reason,
                json.dumps({"timestamp": datetime.now().isoformat()}),
            ),
        )

        conn.commit()
        conn.close()

        logger.info(f"Saved no-contact reason for contact {contact_id}: {reason}")
        return True

    except Exception as e:
        logger.error(f"Error saving no-contact reason: {e}")
        return False


def save_seller_selection_data(contact_id, sellers):
    """
    Зберігає інформацію про відправлені опції вибору продавців

    Args:
        contact_id: ID контакта
        sellers: Список кортежів (name, last_name) продавців
    """
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        # Підготовка даних для JSON
        sellers_data = [
            {"name": name, "last_name": last_name} for name, last_name in sellers
        ]

        # Зберігаємо інформацію про показані опції
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
                "seller_selection_options",
                f"Shown {len(sellers)} sellers",
                json.dumps(
                    {"sellers": sellers_data, "timestamp": datetime.now().isoformat()}
                ),
            ),
        )

        conn.commit()
        conn.close()

        logger.info(f"Saved seller selection options for contact {contact_id}")
        return True

    except Exception as e:
        logger.error(f"Error saving seller selection data: {e}")
        if "conn" in locals():
            conn.close()
        return False
