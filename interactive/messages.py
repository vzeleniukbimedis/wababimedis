import logging
import json
from datetime import datetime
from .utils import format_seller_name
from sendpulse.api import get_sendpulse_token
import requests

logger = logging.getLogger(__name__)


def create_seller_selection_message(bot_id, phone, sellers):
    """
    Створює структуру інтерактивного повідомлення з вибором продавця

    Args:
        bot_id: ID бота в SendPulse
        phone: Номер телефону користувача
        sellers: Список кортежів (name, last_name) продавців
    """
    try:
        logger.info(
            f"Creating seller selection message for {phone} with {len(sellers)} sellers"
        )

        # Створюємо кнопки для кожного продавця
        buttons = []
        for name, last_name in sellers:
            button_text = format_seller_name(name, last_name)
            button_id = f"{name}_{last_name}".replace(" ", "_")

            buttons.append(
                {"type": "reply", "reply": {"id": button_id, "title": button_text}}
            )

        logger.debug(f"Created buttons: {json.dumps(buttons, indent=2)}")

        # Обмеження WhatsApp - максимум 3 кнопки
        buttons = buttons[:3]

        # Отримати contact_id з SendPulse API
        token = get_sendpulse_token()
        if not token:
            logger.error("Failed to get SendPulse token")
            return None

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Перевірити чи існує контакт в SendPulse
        check_url = "https://api.sendpulse.com/whatsapp/contacts/getByPhone"
        check_params = {"phone": phone, "bot_id": bot_id}
        logger.debug(f"Checking contact with params: {check_params}")
        response = requests.get(check_url, headers=headers, params=check_params)
        logger.debug(f"Check contact response: {response.status_code} {response.text}")

        contact_id = None
        if response.status_code == 200:
            contact_data = response.json()
            contact_id = contact_data.get("data", {}).get("id")
            logger.info(f"Found existing contact: {contact_id}")

        if not contact_id:
            # Створити новий контакт, якщо не існує
            create_url = "https://api.sendpulse.com/whatsapp/contacts/add"
            create_data = {"phone": phone, "bot_id": bot_id}
            logger.debug(f"Creating new contact with data: {create_data}")
            create_response = requests.post(
                create_url, headers=headers, json=create_data
            )
            logger.debug(
                f"Create contact response: {create_response.status_code} {create_response.text}"
            )

            if create_response.status_code == 200:
                contact_id = create_response.json().get("data", {}).get("id")
                logger.info(f"Created new contact: {contact_id}")
            else:
                logger.error(f"Failed to create contact: {create_response.text}")
                return None

        message = {
            "bot_id": bot_id,
            "phone": phone,
            "contact_id": contact_id,
            "message": {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": "What seller are you currently in contact with?"},
                    "action": {"buttons": buttons},
                },
            },
        }

        logger.debug(f"Created message structure: {json.dumps(message, indent=2)}")
        return message

    except Exception as e:
        logger.error(f"Error creating seller selection message: {e}", exc_info=True)
        return None


def create_no_contact_reason_message(bot_id, phone):
    """
    Створює повідомлення з питанням чому не вдалося зв'язатися з продавцем

    Args:
        bot_id: ID бота в SendPulse
        phone: Номер телефону користувача
    """
    try:
        logger.info(f"Creating no-contact reason message for {phone}")

        # Створюємо кнопки з причинами
        buttons = [
            {
                "type": "reply",
                "reply": {"id": "seller_not_replying", "title": "Seller not replying"},
            },
            {
                "type": "reply",
                "reply": {"id": "no_time_to_contact", "title": "No time to contact"},
            },
        ]

        # Отримати contact_id з SendPulse API
        token = get_sendpulse_token()
        if not token:
            logger.error("Failed to get SendPulse token")
            return None

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Перевірити чи існує контакт в SendPulse
        check_url = "https://api.sendpulse.com/whatsapp/contacts/getByPhone"
        check_params = {"phone": phone, "bot_id": bot_id}
        logger.debug(f"Checking contact with params: {check_params}")
        response = requests.get(check_url, headers=headers, params=check_params)
        logger.debug(f"Check contact response: {response.status_code} {response.text}")

        contact_id = None
        if response.status_code == 200:
            contact_data = response.json()
            contact_id = contact_data.get("data", {}).get("id")
            logger.info(f"Found existing contact: {contact_id}")

        if not contact_id:
            # Створити новий контакт, якщо не існує
            create_url = "https://api.sendpulse.com/whatsapp/contacts/add"
            create_data = {"phone": phone, "bot_id": bot_id}
            logger.debug(f"Creating new contact with data: {create_data}")
            create_response = requests.post(
                create_url, headers=headers, json=create_data
            )
            logger.debug(
                f"Create contact response: {create_response.status_code} {create_response.text}"
            )

            if create_response.status_code == 200:
                contact_id = create_response.json().get("data", {}).get("id")
                logger.info(f"Created new contact: {contact_id}")
            else:
                logger.error(f"Failed to create contact: {create_response.text}")
                return None

        message = {
            "bot_id": bot_id,
            "phone": phone,
            "contact_id": contact_id,
            "message": {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": "Why didn't you manage to get in touch with the seller?"
                    },
                    "action": {"buttons": buttons},
                },
            },
        }

        logger.debug(
            f"Created no-contact reason message: {json.dumps(message, indent=2)}"
        )
        return message

    except Exception as e:
        logger.error(f"Error creating no-contact reason message: {e}", exc_info=True)
        return None


def create_error_message(bot_id, phone, error_text):
    """
    Створює повідомлення про помилку

    Args:
        bot_id: ID бота в SendPulse
        phone: Номер телефону користувача
        error_text: Текст помилки
    """
    try:
        logger.info(f"Creating error message for {phone}")

        message = {
            "bot_id": bot_id,
            "phone": phone,
            "message": {"type": "text", "text": error_text},
        }

        logger.debug(f"Created error message: {json.dumps(message, indent=2)}")
        return message

    except Exception as e:
        logger.error(f"Error creating error message: {e}", exc_info=True)
        return None


def create_template_message(bot_id, phone, template_name, template_data=None):
    """
    Створює повідомлення на основі шаблону

    Args:
        bot_id: ID бота в SendPulse
        phone: Номер телефону користувача
        template_name: Назва шаблону
        template_data: Дані для шаблону (опціонально)
    """
    try:
        logger.info(f"Creating template message '{template_name}' for {phone}")

        message = {
            "bot_id": bot_id,
            "phone": phone,
            "template": {"name": template_name, "language": {"code": "en"}},
        }

        # Додаємо параметри шаблону, якщо вони є
        if template_data:
            message["template"]["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(value)} for value in template_data
                    ],
                }
            ]

        logger.debug(f"Created template message: {json.dumps(message, indent=2)}")
        return message

    except Exception as e:
        logger.error(f"Error creating template message: {e}", exc_info=True)
        return None


def create_support_message(bot_id, phone):
    """
    Створює повідомлення з контактами підтримки

    Args:
        bot_id: ID бота в SendPulse
        phone: Номер телефону користувача
    """
    try:
        logger.info(f"Creating support message for {phone}")

        message = {
            "bot_id": bot_id,
            "phone": phone,
            "message": {
                "type": "text",
                "text": (
                    "If you need any assistance, please contact our support team:\n\n"
                    "📧 Email: support@bimedis.com\n"
                    "🌐 Website: https://bimedis.com\n"
                    "⏰ Working hours: 24/7"
                ),
            },
        }

        logger.debug(f"Created support message: {json.dumps(message, indent=2)}")
        return message

    except Exception as e:
        logger.error(f"Error creating support message: {e}", exc_info=True)
        return None
