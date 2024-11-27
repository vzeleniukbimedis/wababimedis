import logging
import sqlite3
import json
from datetime import datetime

logger = logging.getLogger(__name__)


def get_sellers_for_contact(contact_id):
    """
    Отримує всіх продавців, пов'язаних з контактом через угоди

    Args:
        contact_id: ID контакта
    """
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT ds.name, ds.last_name
            FROM DealSellers ds
            JOIN Deals d ON ds.deal_id = d.id
            WHERE d.contact_id = ?
        """,
            (contact_id,),
        )

        sellers = cursor.fetchall()
        conn.close()

        logger.info(f"Found {len(sellers)} sellers for contact {contact_id}")
        return sellers

    except Exception as e:
        logger.error(f"Error getting sellers for contact {contact_id}: {e}")
        if "conn" in locals():
            conn.close()
        return []


def format_seller_name(name, last_name):
    """
    Форматує ім'я продавця для відображення на кнопці

    Args:
        name: Ім'я продавця
        last_name: Прізвище продавця
    """
    try:
        full_name = f"{name} {last_name}".strip()
        if len(full_name) > 20:
            return full_name[:17] + "..."
        return full_name

    except Exception as e:
        logger.error(f"Error formatting seller name: {e}")
        return f"{name} {last_name}"


def check_message_exists(contact_id, template_name, timeframe_minutes=5):
    """
    Перевіряє чи було відправлено повідомлення за останні N хвилин

    Args:
        contact_id: ID контакта
        template_name: Назва шаблону
        timeframe_minutes: Часовий проміжок в хвилинах
    """
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM messages
            WHERE contact_id = ?
            AND template_name = ?
            AND created_at >= datetime('now', '-' || ? || ' minutes')
        """,
            (contact_id, template_name, timeframe_minutes),
        )

        count = cursor.fetchone()[0]
        conn.close()

        return count > 0

    except Exception as e:
        logger.error(f"Error checking message existence: {e}")
        if "conn" in locals():
            conn.close()
        return False


def count_seller_selections(seller_id, timeframe_days=30):
    """
    Підраховує скільки разів продавця вибирали за період

    Args:
        seller_id: ID продавця
        timeframe_days: Часовий проміжок в днях
    """
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        query = """
            SELECT COUNT(*)
            FROM message_responses
            WHERE template_name = 'seller_selected'
            AND json_extract(additional_data, '$.seller_id') = ?
            AND created_at >= datetime('now', '-' || ? || ' days')
        """

        cursor.execute(query, (seller_id, timeframe_days))

        count = cursor.fetchone()[0]
        conn.close()

        return count

    except Exception as e:
        logger.error(f"Error counting seller selections: {e}")
        if "conn" in locals():
            conn.close()
        return 0


def log_message_event(contact_id, event_type, details=None):
    """
    Логує подію, пов'язану з повідомленням

    Args:
        contact_id: ID контакта
        event_type: Тип події
        details: Додаткові деталі (опціонально)
    """
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        query = """
            INSERT INTO message_responses 
            (contact_id, template_name, response_text, additional_data)
            VALUES (?, ?, ?, ?)
        """

        cursor.execute(
            query,
            (
                contact_id,
                f"event_{event_type}",
                "",
                (
                    json.dumps(
                        {"details": details, "timestamp": datetime.now().isoformat()}
                    )
                    if details
                    else None
                ),
            ),
        )

        conn.commit()
        conn.close()

        logger.info(f"Logged message event {event_type} for contact {contact_id}")

    except Exception as e:
        logger.error(f"Error logging message event: {e}")
        if "conn" in locals():
            conn.close()


def get_contact_message_count(contact_id, template_name=None, status=None):
    """
    Підраховує кількість повідомлень для контакта

    Args:
        contact_id: ID контакта
        template_name: Фільтр за шаблоном (опціонально)
        status: Фільтр за статусом (опціонально)
    """
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        query = "SELECT COUNT(*) FROM messages WHERE contact_id = ?"
        params = [contact_id]

        if template_name:
            query += " AND template_name = ?"
            params.append(template_name)

        if status is not None:
            query += " AND status = ?"
            params.append(status)

        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        conn.close()

        return count

    except Exception as e:
        logger.error(f"Error getting message count: {e}")
        if "conn" in locals():
            conn.close()
        return 0


def save_message_response(contact_id, template_name, response, details=None):
    """
    Зберігає відповідь на повідомлення

    Args:
        contact_id: ID контакта
        template_name: Назва шаблону
        response: Текст відповіді
        details: Додаткові деталі (опціонально)
    """
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        query = """
            INSERT INTO message_responses 
            (contact_id, template_name, response_text, additional_data)
            VALUES (?, ?, ?, ?)
        """

        additional_data = {"timestamp": datetime.now().isoformat()}
        if details:
            additional_data.update(details)

        cursor.execute(
            query, (contact_id, template_name, response, json.dumps(additional_data))
        )

        conn.commit()
        conn.close()

        logger.info(f"Saved response for contact {contact_id}: {response}")
        return True

    except Exception as e:
        logger.error(f"Error saving message response: {e}")
        if "conn" in locals():
            conn.close()
        return False


def check_contact_exists(contact_id):
    """
    Перевіряє чи існує контакт в базі

    Args:
        contact_id: ID контакта
    """
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM Contacts WHERE id = ?", (contact_id,))
        exists = cursor.fetchone()[0] > 0
        conn.close()

        return exists

    except Exception as e:
        logger.error(f"Error checking contact existence: {e}")
        if "conn" in locals():
            conn.close()
        return False
