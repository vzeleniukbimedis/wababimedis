import os
import logging
from dotenv import load_dotenv

load_dotenv()

# SendPulse конфігурація
SENDPULSE_API_USER_ID = os.getenv("SENDPULSE_API_USER_ID")
SENDPULSE_API_SECRET = os.getenv("SENDPULSE_API_SECRET")
SENDPULSE_WHATSAPP_BOT_ID = os.getenv("SENDPULSE_WHATSAPP_BOT_ID")

# SMTP конфігурація
SMTP_CONFIG = {
    "SERVER": "mail2.softimus.org",
    "PORT": 587,
    "USERNAME": "bimedis.support@bimedis.com",
    "PASSWORD": "Jor34niGDmb31",
    "FROM": "bimedis.support@bimedis.com",
    "TO": "zelenykvd@gmail.com",
}


def init_app(app):
    """Ініціалізація налаштувань додатку"""
    # Налаштування логування
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )

    # Додавання конфігурації до Flask app
    app.config.update(
        SENDPULSE_API_USER_ID=SENDPULSE_API_USER_ID,
        SENDPULSE_API_SECRET=SENDPULSE_API_SECRET,
        SENDPULSE_WHATSAPP_BOT_ID=SENDPULSE_WHATSAPP_BOT_ID,
        SMTP_CONFIG=SMTP_CONFIG,
    )
