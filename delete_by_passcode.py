import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "congReport.db"

# ⚠️ SET THE PASSCODE YOU WANT TO DELETE HERE
TARGET_PASSCODE = "your_passcode_here"


def delete_records_by_passcode(passcode: str):
    if not passcode or passcode == "your_passcode_here":
        print("❌ Error: Please specify a valid TARGET_PASSCODE before running.")
        return

    if not DB_FILE.exists():
        print(f"❌ Error: Database file not found at {DB_FILE}")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Tables to wipe records from
    target_tables = ["CongInfo", "GROUPS", "PUBLISHERS", "MonthlyRecords", "RECORDS"]

    try:
        print(f"🔍 Starting deletion process for passcode: '{passcode}'...\n")
        total_deleted = 0

        # Verify existing tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = {row[0] for row in cursor.fetchall()}

        for table in target_tables:
            if table in existing_tables:
                cursor.execute(f"DELETE FROM {table} WHERE passcode = ?", (passcode,))
                deleted_count = cursor.rowcount
                total_deleted += deleted_count
                print(f"   🗑️  [{table}] Deleted {deleted_count} row(s)")

        conn.commit()
        print(f"\n✅ Successfully deleted {total_deleted} total record(s) for passcode '{passcode}'.")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error during deletion: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    delete_records_by_passcode(TARGET_PASSCODE)