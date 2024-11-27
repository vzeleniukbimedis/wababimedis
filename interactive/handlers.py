import logging
import requests
from flask import current_app
import sqlite3
import json
from datetime import datetime
from .messages import (
    create_seller_selection_message,
    create_no_contact_reason_message,
    create_error_message,
)
from .utils import get_sellers_for_contact
from sendpulse.api import get_sendpulse_token
from database.db_operations import (
    save_whatsapp_message,
    get_contact_by_phone,
    save_no_contact_reason,
    save_seller_selection_data,
)

logger = logging.getLogger(__name__)


def handle_days4_yes_response(contact_id, phone):
    """Обробляє позитивну відповідь на days4 повідомлення"""
    try:
        logger.info(
            f"Processing days4 YES response for contact {contact_id} with phone {phone}"
        )

        # Перевіряємо чи існує контакт
        contact = get_contact_by_phone(phone)
        if not contact:
            logger.error(f"Contact not found for phone {phone}")
            return False

        token = get_sendpulse_token()
        if not token:
            logger.error("Failed to get SendPulse token")
            return False

        sellers = get_sellers_for_contact(contact["id"])
        logger.info(f"Found sellers for contact {contact['id']}: {sellers}")

        if not sellers:
            logger.error(f"No sellers found for contact {contact['id']}")
            # Якщо продавців немає, відправляємо повідомлення про це
            payload = create_error_message(
                current_app.config["SENDPULSE_WHATSAPP_BOT_ID"],
                phone,
                "We apologize, but we couldn't find any sellers associated with your inquiry. "
                "Our support team will contact you shortly.",
            )
        else:
            logger.info(
                f"Creating message with {len(sellers)} sellers for contact {contact['id']}"
            )
            payload = create_seller_selection_message(
                current_app.config["SENDPULSE_WHATSAPP_BOT_ID"], phone, sellers
            )

        if payload is None:
            logger.error("Failed to create message payload")
            return False

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        url = "https://api.sendpulse.com/whatsapp/contacts/send"
        logger.debug(f"Sending request to SendPulse: {payload}")

        response = requests.post(url, headers=headers, json=payload)
        logger.debug(f"SendPulse response: {response.status_code} {response.text}")

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("success"):
                message_details = {
                    "data": {
                        "whatsapp_message_id": response_data["data"]["data"].get(
                            "message_id"
                        ),
                        "sendpulse_message_id": response_data["data"].get("id"),
                        "sendpulse_contact_id": payload.get("contact_id"),
                        "status": response_data["data"].get("status", 1),
                    }
                }

                template_name = "seller_selection" if sellers else "no_sellers_found"
                save_whatsapp_message(
                    contact_id=contact["id"],
                    template_name=template_name,
                    message_details=message_details,
                )

                # Зберігаємо додаткову інформацію про відправлені кнопки
                if sellers:
                    save_seller_selection_data(contact["id"], sellers)

                logger.info(f"Successfully sent {template_name} message to {phone}")
                return True

        logger.error(f"Failed to send message: {response.text}")
        return False

    except Exception as e:
        logger.error(f"Error in handle_days4_yes_response: {e}", exc_info=True)
        return False


def handle_days4_no_response(contact_id, phone):
    """Обробляє негативну відповідь на days4 повідомлення"""
    try:
        logger.info(
            f"Processing days4 NO response for contact {contact_id} with phone {phone}"
        )

        token = get_sendpulse_token()
        if not token:
            logger.error("Failed to get SendPulse token")
            return False

        payload = create_no_contact_reason_message(
            current_app.config["SENDPULSE_WHATSAPP_BOT_ID"], phone
        )

        if not payload:
            logger.error("Failed to create no-contact reason message")
            return False

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        url = "https://api.sendpulse.com/whatsapp/contacts/send"
        logger.debug(f"Sending request to SendPulse: {payload}")

        response = requests.post(url, headers=headers, json=payload)
        logger.debug(f"SendPulse response: {response.status_code} {response.text}")

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("success"):
                # Зберігаємо інформацію про відправлене повідомлення
                message_details = {
                    "data": {
                        "whatsapp_message_id": response_data["data"]["data"].get(
                            "message_id"
                        ),
                        "sendpulse_message_id": response_data["data"].get("id"),
                        "sendpulse_contact_id": payload.get("contact_id"),
                        "status": response_data["data"].get("status", 1),
                    }
                }

                save_whatsapp_message(
                    contact_id=contact_id,
                    template_name="days4_no_reason_request",
                    message_details=message_details,
                )

                logger.info(f"Successfully sent no-contact reason request to {phone}")
                return True

        logger.error(f"Failed to send message: {response.text}")
        return False

    except Exception as e:
        logger.error(f"Error in handle_days4_no_response: {e}", exc_info=True)
        return False


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

        # Формуємо текст підтвердження з деталями
        confirmation_text = (
            f"Thank you for confirming! We've recorded that you're in contact with "
            f"{seller_data['name']} {seller_data['last_name']}.\n\n"
            "If you need any additional assistance or have questions, "
            "feel free to contact our support team."
        )

        payload = {
            "bot_id": current_app.config["SENDPULSE_WHATSAPP_BOT_ID"],
            "phone": phone,
            "message": {"type": "text", "text": confirmation_text},
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        url = "https://api.sendpulse.com/whatsapp/contacts/send"
        logger.debug(f"Sending confirmation message to SendPulse: {payload}")

        response = requests.post(url, headers=headers, json=payload)
        logger.debug(f"SendPulse response: {response.status_code} {response.text}")

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
                    template_name="seller_confirmation",
                    message_details=message_details,
                )

                # Зберігаємо вибір продавця
                save_seller_choice(contact["id"], seller_data)

                logger.info(
                    f"Successfully sent confirmation for seller selection to {phone}"
                )
                return True

        logger.error(f"Failed to send confirmation message: {response.text}")
        return False

    except Exception as e:
        logger.error(f"Error handling button response: {e}", exc_info=True)
        return False


def handle_error_message(phone, error_message):
    """Відправляє повідомлення про помилку користувачу"""
    try:
        token = get_sendpulse_token()
        if not token:
            logger.error("Failed to get SendPulse token")
            return False

        payload = create_error_message(
            current_app.config["SENDPULSE_WHATSAPP_BOT_ID"], phone, error_message
        )

        if not payload:
            logger.error("Failed to create error message")
            return False

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            "https://api.sendpulse.com/whatsapp/contacts/send",
            headers=headers,
            json=payload,
        )

        success = response.status_code == 200
        if success:
            logger.info(f"Successfully sent error message to {phone}")
        else:
            logger.error(f"Failed to send error message: {response.text}")

        return success

    except Exception as e:
        logger.error(f"Error sending error message: {e}")
        return False


def get_seller_info_from_button(button_id):
    """Отримує інформацію про продавця з ID кнопки"""
    try:
        # Розбираємо ID кнопки на ім'я та прізвище
        name_parts = button_id.split("_")
        if len(name_parts) < 2:
            logger.error(f"Invalid button_id format: {button_id}")
            return None

        # Знаходимо продавця в базі
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 
                id, name, last_name, email, phone
            FROM DealSellers
            WHERE name = ? AND last_name = ?
            LIMIT 1
        """,
            (name_parts[0], name_parts[1]),
        )

        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                "id": result[0],
                "name": result[1],
                "last_name": result[2],
                "email": result[3],
                "phone": result[4],
            }

        return None

    except Exception as e:
        logger.error(f"Error getting seller info from button: {e}")
        return None


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
                        "seller_id": seller_data.get("id"),
                        "seller_email": seller_data.get("email"),
                        "seller_phone": seller_data.get("phone"),
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
