import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def init_db():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in the .env file.")

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    try:
        # 1. CongInfo Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS "CongInfo" (
                "NUM" INTEGER,
                "Congregation" TEXT,
                "CongNumber" TEXT,
                "Address" TEXT,
                "Province" TEXT,
                "CBOE" TEXT,
                "SO" TEXT,
                "SEC" TEXT,
                passcode TEXT PRIMARY KEY,
                "User" TEXT
            );
        """
        )

        # 2. GROUPS Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS "GROUPS" (
                id SERIAL PRIMARY KEY,
                "Group_" TEXT,
                "Overseer" TEXT,
                "Assistant" TEXT,
                "MeetingPlace" TEXT,
                "Remarks" TEXT,
                passcode TEXT
            );
        """
        )

        # 3. PUBLISHERS Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS "PUBLISHERS" (
                "IDPub" TEXT,
                "FNAME" TEXT,
                "MName" TEXT,
                "LName" TEXT,
                "Nname" TEXT,
                "Birthdate" DATE,
                "Male" INTEGER,
                "Female" INTEGER,
                "Address" TEXT,
                "TelCp" TEXT,
                "Baptism" DATE,
                "Elder" INTEGER,
                "MS" INTEGER,
                "RP" INTEGER,
                "RpNumber" TEXT,
                "RpDateStarted" DATE,
                "GROUP_" TEXT,
                "Status" TEXT,
                "Started" INTEGER,
                "SF" INTEGER,
                passcode TEXT,
                PRIMARY KEY ("IDPub", passcode)
            );
        """
        )

        # 4. MonthlyRecords Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS "MonthlyRecords" (
                "ID" SERIAL PRIMARY KEY,
                "NUMBER" INTEGER,
                "MONTH_" TEXT,
                "Year" INTEGER,
                "ServiceYear" INTEGER,
                "AttendcMidweekTotal" INTEGER,
                "AttendcPublickTotal" INTEGER,
                "NoMtgs1" INTEGER,
                "NoMtgs2" INTEGER,
                "ActivePublishers" INTEGER,
                passcode TEXT
            );
        """
        )

        # 5. RECORDS Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS "RECORDS" (
                id SERIAL PRIMARY KEY,
                "IdPubs" TEXT,
                "NUMBER" INTEGER,
                "Date_entered" INTEGER,
                "HRS" NUMERIC,
                "BS" NUMERIC,
                "AUX" TEXT,
                "REMARKS" TEXT,
                "Note" TEXT,
                "MINISTRY" TEXT,
                passcode TEXT
            );
        """
        )

        conn.commit()
        print(" Successfully created all PostgreSQL tables in Neon!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Failed to create tables: {e}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    init_db()