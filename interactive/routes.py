from flask import jsonify, request
import logging
from . import interactive_blueprint
from .handlers import (
    handle_days4_yes_response,
    handle_days4_no_response,
    handle_button_response,
    handle_error_message,
)
from .messages import (
    create_seller_selection_message,
    create_no_contact_reason_message,
    create_error_message,
)
from database.db_operations import (
    get_contact_by_email,
    get_contact_by_phone,
    get_seller_responses_stats,
    get_contact_messages,
    save_no_contact_reason,
)
from sendpulse.api import get_sendpulse_token
import requests
import json

logger = logging.getLogger(__name__)


@interactive_blueprint.route("/webhook", methods=["POST"])
def webhook():
    """Обробляє вебхуки від SendPulse"""
    try:
        data = request.get_json()
        logger.info(f"Received webhook data: {data}")

        if not data or not isinstance(data, list):
            logger.warning("Received empty or invalid webhook data")
            return jsonify({"status": "success", "message": "No data to process"})

        for message_data in data:
            try:
                # Отримуємо інформацію про повідомлення
                info = message_data.get("info", {})
                message_info = info.get("message", {})
                channel_data = message_info.get("channel_data", {})
                message = channel_data.get("message", {})
                contact = message_data.get("contact", {})
                phone = contact.get("phone")
                name = contact.get("name")

                logger.info(
                    f"""
                Processed message data:
                Phone: {phone}
                Name: {name}
                Message type: {message.get('type')}
                Full message: {message}
                """
                )

                if message.get("type") == "button":
                    button_data = message.get("button", {})
                    button_text = button_data.get("text")
                    button_payload = button_data.get("payload")

                    logger.info(
                        f"""
                    Processing button response:
                    Phone: {phone}
                    Name: {name}
                    Button Text: {button_text}
                    Button Payload: {button_payload}
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

                    # Відповідь на питання про комунікацію з продавцем
                    if button_payload in ["fine", "no_reply"]:
                        response_text = (
                            "everything_fine"
                            if button_payload == "fine"
                            else "no_reply"
                        )
                        save_message_response(
                            contact_id=contact_data["id"],
                            template_name="seller_communication",
                            response=response_text,
                        )

                        # Відправляємо підтвердження
                        confirmation_text = (
                            "Thank you for your feedback!"
                            if button_payload == "fine"
                            else "Thank you for your feedback. Our support team will look into this."
                        )

                        handle_error_message(phone, confirmation_text)

                elif message.get("type") == "text":
                    # Обробка текстових повідомлень якщо потрібно
                    text = message.get("text", "")
                    logger.info(f"Received text message: {text} from {phone}")

            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
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
