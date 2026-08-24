import sqlite3

DB_FILE = "congReport.db"


def inspect_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    print("=== DATABASE TABLES & ROW COUNTS ===")
    for (table_name,) in tables:
        if table_name.startswith("sqlite_"):
            continue
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"Table '{table_name}': {count} row(s)")

    print("\n=== SAMPLE MONTH RECORDS ===")
    try:
        cursor.execute("SELECT * FROM MONTH LIMIT 5;")
        rows = cursor.fetchall()
        for row in rows:
            print(row)
    except sqlite3.OperationalError:
        print("MONTH table does not exist yet.")

    conn.close()


if __name__ == "__main__":
    inspect_db()