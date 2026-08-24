import sqlite3

DB_FILE = "congReport.db"


def init_database(db_file: str = DB_FILE):
    """Creates a fresh congReport.db database with all tables including passcode schema."""
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    try:
        # Table Schema Definitions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS MONTH (
                MONTH_ TEXT, NUM INTEGER, Congregation TEXT, CongNumber TEXT, 
                Address TEXT, Province TEXT, CBOE TEXT, SO TEXT, SEC TEXT,
                passcode TEXT,User TEXT            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS GROUPS (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                Group_ TEXT, Overseer TEXT, Assistant TEXT, MeetingPlace TEXT, Remarks TEXT,
                passcode TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS PUBLISHERS (
                IDPub TEXT, FNAME TEXT, MName TEXT, LName TEXT, Nname TEXT, 
                Birthdate TEXT, Male TEXT, Female TEXT, Address TEXT, TelCp TEXT, 
                Baptism TEXT, Elder TEXT, MS TEXT, RP TEXT, RpNumber TEXT, 
                RpDateStarted TEXT, GROUP_ TEXT, Status TEXT, Started INTEGER,
                passcode TEXT,
                PRIMARY KEY (IDPub, passcode)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS MonthlyRecords (
                ID INTEGER PRIMARY KEY AUTOINCREMENT, NUMBER INTEGER, MONTH_ TEXT, 
                Year INTEGER, ServiceYear INTEGER, AttendcMidweekTotal INTEGER, 
                AttendcPublickTotal INTEGER, NoMtgs1 INTEGER, NoMtgs2 INTEGER, ActivePublishers INTEGER,
                passcode TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS RECORDS (
                IdPubs TEXT, NUMBER INTEGER, Date_entered INTEGER, 
                HRS REAL, AUX TEXT, REMARKS TEXT, Note TEXT,
                passcode TEXT
            )
        """)

        # Performance Indexes for multi-tenant filtering
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_publishers_passcode ON PUBLISHERS(passcode);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_passcode ON RECORDS(passcode);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_groups_passcode ON GROUPS(passcode);"
        )

        conn.commit()
        print(
            f"Successfully initialized '{db_file}' with passcode support and indexes."
        )

    except Exception as e:
        conn.rollback()
        print(f"Error initializing database: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_database()