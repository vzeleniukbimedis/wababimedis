import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_db_structure():
    """Перевіряє структуру всіх таблиць в базі даних"""
    try:
        conn = sqlite3.connect("deals_data.db")
        cursor = conn.cursor()

        # Отримуємо список всіх таблиць
        cursor.execute(
            """
            SELECT name 
            FROM sqlite_master 
            WHERE type='table'
        """
        )
        tables = cursor.fetchall()

        print("\n=== Database Tables Structure ===\n")

        for table in tables:
            table_name = table[0]
            print(f"\nTable: {table_name}")
            print("-" * (len(table_name) + 7))

            # Отримуємо інформацію про колонки
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()

            for col in columns:
                print(
                    f"Column: {col[1]}, Type: {col[2]}, NotNull: {col[3]}, DefaultValue: {col[4]}, PK: {col[5]}"
                )

            # Отримуємо кількість записів
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"\nTotal records: {count}")

            # Якщо є записи, показуємо перший для прикладу
            if count > 0:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 1")
                sample = cursor.fetchone()
                print(f"Sample record: {sample}")

            print("\n" + "=" * 50)

        conn.close()

    except Exception as e:
        logger.error(f"Error checking database structure: {e}")
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    check_db_structure()
