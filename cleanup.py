import sqlite3

conn = sqlite3.connect("ozon_assistant.db")

cursor = conn.cursor()

cursor.execute(
    """
    DELETE FROM actions
    WHERE action LIKE '%FBS%'
    """
)

conn.commit()
conn.close()

print("Готово")