from flask import jsonify, request, current_app
import logging
import sqlite3
from datetime import datetime
import json
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

# Import blueprint from __init__.py
from . import interactive_blueprint

from database.db_operations import (
    get_contact_by_email,
    get_contact_by_phone,
    get_seller_responses_stats,
    get_contact_messages,
    save_no_contact_reason,
    save_whatsapp_message,
    save_email_message,
    save_seller_choice,
)
from sendpulse.api import get_sendpulse_token
from .handlers import (
    handle_days4_yes_response,
    handle_days4_no_response,
    handle_error_message,
)

logger = logging.getLogger(__name__)


def get_all_seller_names():
    """Повертає список всіх можливих імен продавців"""
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT name || ' ' || last_name as full_name 
            FROM DealSellers
        """
        )

        sellers = [row[0] for row in cursor.fetchall()]
        conn.close()

        return sellers
    except Exception as e:
        logger.error(f"Error getting seller names: {e}")
        return []


def save_communication_status(contact_id, status):
    """Зберігає статус комунікації з продавцем"""
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
                "seller_communication",
                status,
                json.dumps({"timestamp": datetime.now().isoformat()}),
            ),
        )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        logger.error(f"Error saving communication status: {e}")
        return False


def send_buying_consideration_message(phone, contact_id):
    token = get_sendpulse_token()
    if token:
        buttons = [
            {"type": "reply", "reply": {"id": "yes_buy", "title": "Yes"}},
            {"type": "reply", "reply": {"id": "no_buy", "title": "No"}},
        ]
        payload = {
            "bot_id": current_app.config["SENDPULSE_WHATSAPP_BOT_ID"],
            "phone": phone,
            "contact_id": contact_id,
            "message": {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": "Would you consider buying from this seller?"},
                    "action": {"buttons": buttons},
                },
            },
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
        logger.info(f"Second message response: {response.status_code} {response.text}")
        return response.status_code == 200
    return False


def send_simple_message(phone, text, contact_id=None):
    """Відправляє просте текстове інтерактивне повідомлення"""
    token = get_sendpulse_token()
    if token:
        payload = {
            "bot_id": current_app.config["SENDPULSE_WHATSAPP_BOT_ID"],
            "phone": phone,
            "message": {"type": "text", "text": {"body": text}},
        }

        # Додаємо contact_id, якщо він є
        if contact_id:
            payload["contact_id"] = contact_id

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = "https://api.sendpulse.com/whatsapp/contacts/send"

        response = requests.post(url, headers=headers, json=payload)
        logger.info(f"Simple message response: {response.status_code} {response.text}")
        return response.status_code == 200
    logger.error("Failed to send simple message: Missing token.")
    return False


def send_no_contact_reason_message(phone, contact_id):
    """Відправляє інтерактивне повідомлення з варіантами причин для 'No' відповіді"""
    token = get_sendpulse_token()
    if token:
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
        payload = {
            "bot_id": current_app.config["SENDPULSE_WHATSAPP_BOT_ID"],
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
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = "https://api.sendpulse.com/whatsapp/contacts/send"

        response = requests.post(url, headers=headers, json=payload)
        logger.info(
            f"No-contact reason message response: {response.status_code} {response.text}"
        )
        return response.status_code == 200
    logger.error("Failed to send no-contact reason message: Missing token.")
    return False


@interactive_blueprint.route("/webhook", methods=["POST"])
def webhook():
    """Основний обробник вебхуків"""
    try:
        data = request.get_json()
        logger.info(f"Received webhook data: {json.dumps(data, indent=2)}")

        if not data or not isinstance(data, list):
            logger.warning("Received empty or invalid webhook data")
            return jsonify({"status": "success", "message": "No data to process"})

        for message_data in data:
            try:
                channel_data = (
                    message_data.get("info", {})
                    .get("message", {})
                    .get("channel_data", {})
                )
                message = channel_data.get("message", {})
                contact = message_data.get("contact", {})
                phone = contact.get("phone")
                contact_id = contact.get("id")

                logger.info(f"Processing message: {json.dumps(message, indent=2)}")

                if message.get("type") == "interactive":
                    interactive_data = message.get("interactive", {})
                    button_reply = interactive_data.get("button_reply", {})
                    button_text = button_reply.get("title")

                    logger.info(
                        f"""
                    Processing interactive response:
                    Phone: {phone}
                    Contact ID: {contact_id}
                    Button Text: {button_text}
                    """
                    )

                    contact_data = get_contact_by_phone(phone)
                    if not contact_data:
                        logger.error(f"Contact not found in database for phone {phone}")
                        handle_error_message(
                            phone,
                            "We're sorry, but we couldn't find your contact information. "
                            "Our support team will contact you shortly.",
                        )
                        continue

                    # Відповідь "Yes" на days4
                    if button_text == "Yes":
                        success = handle_days4_yes_response(contact_data["id"], phone)
                        logger.info(f"Seller selection message sent: {success}")

                    # Відповідь "No" на days4
                    elif button_text == "No":
                        success = handle_days4_no_response(contact_data["id"], phone)
                        logger.info(f"No-contact reason request sent: {success}")

                        # Відправка інтерактивного повідомлення
                        send_no_contact_reason_message(phone, contact_id)
                        logger.info(
                            f"Sent follow-up message for 'No' response in days4."
                        )

                    # Обробка відповіді "Everything is fine"
                    elif button_text == "Everything is fine":
                        save_communication_status(
                            contact_data["id"], "communication_ok"
                        )
                        success = send_buying_consideration_message(phone, contact_id)
                        logger.info(f"Buying consideration message sent: {success}")

                    # Обробка відповіді "No reply from seller"
                    elif button_text == "No reply from seller":
                        save_communication_status(contact_data["id"], "no_reply")
                        logger.info(f"Processed 'No reply from seller' response.")

                        # Відправка інтерактивного повідомлення
                        send_no_contact_reason_message(phone, contact_id)
                        logger.info(
                            f"Sent follow-up message for 'No reply from seller'."
                        )

                    # Обробка відповіді на друге повідомлення (Yes/No)
                    elif button_text in ["Yes", "No"]:
                        decision = "yes_buy" if button_text == "Yes" else "no_buy"
                        save_communication_status(contact_data["id"], decision)

                        if decision == "yes_buy":
                            handle_error_message(
                                phone,
                                "Thank you for your feedback. We'll take it into account!",
                            )
                        else:
                            send_simple_message(
                                phone,
                                "Could you please tell us more about why your cooperation failed with this seller?",
                                contact_id=contact_id,
                            )
                            logger.info(f"Sent follow-up message for 'No' response.")

                    # Обробка відповіді з вибором продавця
                    elif button_reply.get("id", "").startswith("eyJ"):
                        logger.info(f"Processing seller selection for: {button_text}")
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
                                "bot_id": current_app.config[
                                    "SENDPULSE_WHATSAPP_BOT_ID"
                                ],
                                "phone": phone,
                                "contact_id": contact_id,
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
                            logger.info(
                                f"Sending seller communication check: {json.dumps(payload, indent=2)}"
                            )

                            response = requests.post(url, headers=headers, json=payload)
                            logger.info(
                                f"SendPulse response: {response.status_code} {response.text}"
                            )

                            if response.status_code == 200:
                                response_data = response.json()
                                if response_data.get("success"):
                                    message_details = {
                                        "data": {
                                            "whatsapp_message_id": response_data[
                                                "data"
                                            ]["data"].get("message_id"),
                                            "sendpulse_message_id": response_data[
                                                "data"
                                            ].get("id"),
                                            "sendpulse_contact_id": contact_id,
                                            "status": response_data["data"].get(
                                                "status", 1
                                            ),
                                        }
                                    }

                                    save_whatsapp_message(
                                        contact_id=contact_data["id"],
                                        template_name="seller_communication_check",
                                        message_details=message_details,
                                    )

                                    name_parts = button_text.split()
                                    seller_data = {
                                        "name": name_parts[0],
                                        "last_name": (
                                            " ".join(name_parts[1:])
                                            if len(name_parts) > 1
                                            else ""
                                        ),
                                    }
                                    save_seller_choice(contact_data["id"], seller_data)
                                    logger.info(
                                        f"Successfully processed seller selection for {button_text}"
                                    )

                elif message.get("type") == "button":
                    button_data = message.get("button", {})
                    button_text = button_data.get("text")

                    logger.info(
                        f"""
                    Processing button response:
                    Phone: {phone}
                    Button Text: {button_text}
                    """
                    )

                    contact_data = get_contact_by_phone(phone)
                    if not contact_data:
                        logger.error(f"Contact not found in database for phone {phone}")
                        handle_error_message(
                            phone,
                            "We're sorry, but we couldn't find your contact information. "
                            "Our support team will contact you shortly.",
                        )
                        continue

                    if button_text == "Yes":
                        success = handle_days4_yes_response(contact_data["id"], phone)
                        logger.info(f"Processed 'Yes' response for days4: {success}")

                    elif button_text == "No":
                        success = handle_days4_no_response(contact_data["id"], phone)
                        logger.info(f"Processed 'No' response for days4: {success}")

                        send_no_contact_reason_message(phone, contact_id)
                        logger.info(
                            f"Sent follow-up message for 'No' response in days4."
                        )

                elif message.get("type") == "text":
                    text = message.get("text", "")
                    logger.info(f"Received text message: {text} from {phone}")

            except Exception as e:
                logger.error(f"Error processing message: {str(e)}", exc_info=True)
                continue

        return jsonify({"status": "success", "message": "Webhook processed"})

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({"error": str(e)}), 500


@interactive_blueprint.route("/handle_days4_response", methods=["POST"])
def handle_days4_response():
    """Обробляє відповідь на days4 повідомлення"""
    try:
        data = request.get_json()
        email = data.get("email")
        response = data.get("response")

        if not email or not response:
            return jsonify({"error": "Email and response are required"}), 400

        if response.lower() == "yes":
            contact = get_contact_by_email(email)
            if not contact or not contact.get("phone"):
                return jsonify({"error": "Contact not found or no phone number"}), 404

            success = handle_days4_yes_response(contact["id"], contact["phone"])

            if success:
                return jsonify(
                    {"status": "success", "message": "Seller selection message sent"}
                )
            else:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Failed to send seller selection message",
                        }
                    ),
                    500,
                )

        return jsonify({"status": "success", "message": "Response processed"})

    except Exception as e:
        logger.error(f"Error handling days4 response: {e}")
        return jsonify({"error": str(e)}), 500


@interactive_blueprint.route("/message_history/<phone>", methods=["GET"])
def message_history(phone):
    """Отримує історію повідомлень для номера телефону"""
    try:
        contact = get_contact_by_phone(phone)
        if not contact:
            return jsonify({"error": "Contact not found"}), 404

        messages = get_contact_messages(contact["id"])

        return jsonify(
            {
                "status": "success",
                "contact": {
                    "id": contact["id"],
                    "name": contact["name"],
                    "last_name": contact.get("last_name", ""),
                    "phone": contact["phone"],
                    "email": contact.get("email", ""),
                },
                "messages": messages,
            }
        )

    except Exception as e:
        logger.error(f"Error getting message history: {e}")
        return jsonify({"error": str(e)}), 500


@interactive_blueprint.route("/seller_responses/stats", methods=["GET"])
def seller_responses():
    """Отримує статистику відповідей по продавцях"""
    try:
        stats = get_seller_responses_stats()
        return jsonify({"status": "success", "stats": stats})

    except Exception as e:
        logger.error(f"Error getting seller response stats: {e}")
        return jsonify({"error": str(e)}), 500


@interactive_blueprint.route("/resend_seller_selection/<phone>", methods=["POST"])
def resend_seller_selection(phone):
    """Повторно відправляє повідомлення з вибором продавця"""
    try:
        contact = get_contact_by_phone(phone)
        if not contact:
            return jsonify({"error": "Contact not found"}), 404

        success = handle_days4_yes_response(contact["id"], phone)

        if success:
            return jsonify(
                {"status": "success", "message": "Seller selection message resent"}
            )
        else:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Failed to resend seller selection message",
                    }
                ),
                500,
            )

    except Exception as e:
        logger.error(f"Error resending seller selection: {e}")
        return jsonify({"error": str(e)}), 500


@interactive_blueprint.route("/send_error_message", methods=["POST"])
def send_error_message():
    """Відправляє повідомлення про помилку"""
    try:
        data = request.get_json()
        phone = data.get("phone")
        message = data.get("message")

        if not phone or not message:
            return jsonify({"error": "Phone and message are required"}), 400

        success = handle_error_message(phone, message)

        if success:
            return jsonify({"status": "success", "message": "Error message sent"})
        else:
            return (
                jsonify({"status": "error", "message": "Failed to send error message"}),
                500,
            )

    except Exception as e:
        logger.error(f"Error sending error message: {e}")
        return jsonify({"error": str(e)}), 500
