import sqlite3
import logging

logger = logging.getLogger(__name__)


def init_db():
    """Ініціалізація всіх необхідних таблиць бази даних"""
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        # Створення таблиці Contacts, якщо вона не існує
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Contacts (
                id INTEGER PRIMARY KEY,
                name TEXT,
                last_name TEXT,
                phone TEXT,
                email TEXT
            )
        """
        )

        # Створення таблиці Deals, якщо вона не існує
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Deals (
                id INTEGER PRIMARY KEY,
                contact_id INTEGER,
                status INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES Contacts(id)
            )
        """
        )

        # Створення таблиці DealSellers, якщо вона не існує
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS DealSellers (
                id INTEGER PRIMARY KEY,
                deal_id INTEGER,
                name TEXT,
                last_name TEXT,
                email TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (deal_id) REFERENCES Deals(id)
            )
        """
        )

        # Створення таблиці повідомлень
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                message_type VARCHAR(20) NOT NULL,  -- 'whatsapp' або 'email'
                template_name VARCHAR(50),          -- назва шаблону (day1, days4, etc.)
                message_text TEXT,                  -- текст повідомлення
                whatsapp_message_id TEXT,          -- ID повідомлення WhatsApp
                sendpulse_message_id TEXT,         -- ID повідомлення в SendPulse
                sendpulse_contact_id TEXT,         -- ID контакта в SendPulse
                status INTEGER,                    -- статус повідомлення
                status_description TEXT,           -- опис статусу/помилки
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES Contacts(id)
            )
        """
        )

        # Створення таблиці для трекінгу кліків
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS click_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                template_name TEXT NOT NULL,  -- day1, days4, etc.
                response TEXT,                -- yes, no
                user_agent TEXT,
                referrer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES Contacts(id)
            )
        """
        )

        # Створення таблиці для відповідей на повідомлення
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS message_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                template_name TEXT NOT NULL,
                response_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES Contacts(id)
            )
        """
        )

        # Створення індексів для click_tracking
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_click_tracking_contact_id 
            ON click_tracking(contact_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_click_tracking_email 
            ON click_tracking(email)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_click_tracking_template 
            ON click_tracking(template_name)
        """
        )

        # Створення індексів для messages
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_contact_id 
            ON messages(contact_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_type 
            ON messages(message_type)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_template 
            ON messages(template_name)
        """
        )

        # Створення індексів для message_responses
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_message_responses_contact 
            ON message_responses(contact_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_message_responses_template 
            ON message_responses(template_name)
        """
        )

        # Створення індексів для основних таблиць
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_contacts_email 
            ON Contacts(email)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_contacts_phone 
            ON Contacts(phone)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_deals_contact 
            ON Deals(contact_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_deal_sellers_deal 
            ON DealSellers(deal_id)
        """
        )

        conn.commit()
        conn.close()
        logger.info("База даних успішно ініціалізована")
    except Exception as e:
        logger.error(f"Помилка при ініціалізації бази даних: {e}")
        if "conn" in locals():
            conn.close()
        raise


# Викликаємо ініціалізацію при імпорті модуля
if __name__ == "__main__":
    # Налаштування логування
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )

    # Ініціалізація бази даних
    init_db()
    logger.info("Database initialization complete")
else:
    init_db()
