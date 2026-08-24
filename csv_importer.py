import csv
import io
import os
import sqlite3
import logging
import sys
import argparse
from datetime import datetime

logger = logging.getLogger(__name__)
DEFAULT_DB = "congregation.db"

def to_int(val):
    try:
        return int(val) if val is not None and str(val).strip() != "" else None
    except ValueError:
        return None

def to_float(val):
    try:
        return float(val) if val is not None and str(val).strip() != "" else None
    except ValueError:
        return None

def format_date(val):
    if not val or not str(val).strip():
        return ""
    val_str = str(val).strip()
    
    formats = (
        "%d %b %Y %H:%M:%S",  # e.g., "6 Mar 1988 0:00:00"
        "%d %b %Y",           # e.g., "6 Mar 1988"
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    )
    
    for fmt in formats:
        try:
            dt = datetime.strptime(val_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
            
    return val_str

def process_single_csv(
    filename: str,
    content_bytes: bytes,
    passcode: str,
    username: str = "",
    db_file: str = DEFAULT_DB,
) -> str:
    file_base_name = os.path.splitext(os.path.basename(filename))[0].lower()
    decoded_content = content_bytes.decode("latin-1", errors="ignore")
    reader = csv.DictReader(io.StringIO(decoded_content))

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    try:
        if "conginfo" in file_base_name:
                    table_name = "CongInfo"
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS CongInfo (
                            NUM INTEGER, Congregation TEXT, CongNumber TEXT, 
                            Address TEXT, Province TEXT, CBOE TEXT, SO TEXT, SEC TEXT,
                            passcode TEXT, User TEXT
                        )
                    """)
        elif "group" in file_base_name:
            table_name = "GROUPS"
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS GROUPS (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    Group_ TEXT, Overseer TEXT, Assistant TEXT, MeetingPlace TEXT, Remarks TEXT,
                    passcode TEXT
                )
            """)
        elif "publisher" in file_base_name:
                    table_name = "PUBLISHERS"
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS PUBLISHERS (
                            IDPub TEXT, FNAME TEXT, MName TEXT, LName TEXT, Nname TEXT, 
                            Birthdate TEXT, Male INTEGER, Female INTEGER, Address TEXT, TelCp TEXT, 
                            Baptism TEXT, Elder INTEGER, MS INTEGER, RP INTEGER, RpNumber TEXT, 
                            RpDateStarted TEXT, GROUP_ TEXT, Status TEXT, Started INTEGER,
                            passcode TEXT,SF INTEGER,
                            PRIMARY KEY (IDPub, passcode)
                        )
                    """)
        elif "monthlyrecords" in file_base_name:
            table_name = "MonthlyRecords"
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS MonthlyRecords (
                    ID INTEGER PRIMARY KEY AUTOINCREMENT, NUMBER INTEGER, MONTH_ TEXT, 
                    Year INTEGER, ServiceYear INTEGER, AttendcMidweekTotal INTEGER, 
                    AttendcPublickTotal INTEGER, NoMtgs1 INTEGER, NoMtgs2 INTEGER, ActivePublishers INTEGER,
                    passcode TEXT
                )
            """)
        else:
            table_name = "RECORDS"
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS RECORDS (
                    IdPubs INTEGER, NUMBER INTEGER, Date_entered INTEGER, 
                    HRS INTEGER,BS INTEGER, AUX TEXT, REMARKS TEXT, Note TEXT, MINISTRY TEXT,
                    passcode TEXT
                )
            """)

        cursor.execute(
            f"DELETE FROM {table_name} WHERE passcode = ?", (passcode,)
        )

        row_count = 0
        for row in reader:
            clean_row = {
                k.strip(): v for k, v in row.items() if k is not None
            }

            if table_name == "CongInfo":
                cursor.execute(
                    """
                    INSERT INTO CongInfo (NUM, Congregation, CongNumber, Address, Province, CBOE, SO, SEC, passcode, User) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        to_int(clean_row.get("NUM")),
                        clean_row.get("Congregation", ""),
                        clean_row.get("CongNumber", ""),
                        clean_row.get("Address", ""),
                        clean_row.get("Province", ""),
                        clean_row.get("CBOE", ""),
                        clean_row.get("SO", ""),
                        clean_row.get("SEC", ""),
                        passcode,
                        username,
                    ),
                )

            elif table_name == "GROUPS":
                cursor.execute(
                    """
                    INSERT INTO GROUPS (Group_, Overseer, Assistant, MeetingPlace, Remarks, passcode) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        clean_row.get("Group", ""),
                        clean_row.get("Overseer", ""),
                        clean_row.get("Assistant", ""),
                        clean_row.get("MeetingPlace", ""),
                        clean_row.get("Remarks", ""),
                        passcode,
                    ),
                )

            elif table_name == "PUBLISHERS":
                # --- CLEAN AND STANDARDIZE NAMES HERE ---
                fname = (clean_row.get("FNAME") or "").strip()
                mname = (clean_row.get("MName") or "").strip()
                lname = (clean_row.get("LName") or "").strip()
                nname = (clean_row.get("Nname") or "").strip()
                
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO PUBLISHERS (
                        IDPub, FNAME, MName, LName, Nname, Birthdate, Male, Female, 
                        Address, TelCp, Baptism, Elder, MS, RP, RpNumber, 
                        RpDateStarted, GROUP_, Status, Started,SF, passcode
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        clean_row.get("IDPub", ""),
                        fname,   # Cleaned first name
                        mname,   # Cleaned middle name
                        lname,   # Cleaned last name
                        nname,   # Cleaned nickname
                        format_date(clean_row.get("Birthdate")),
                        to_int(clean_row.get("Male")),
                        to_int(clean_row.get("Female")),
                        clean_row.get("Address", ""),
                        clean_row.get("TelCp", ""),
                        format_date(clean_row.get("Baptism")),
                        to_int(clean_row.get("Elder")),
                        to_int(clean_row.get("MS")),
                        to_int(clean_row.get("RP")),
                        clean_row.get("RpNumber", ""),
                        format_date(clean_row.get("RpDateStarted")),
                        clean_row.get("GROUP", ""),
                        clean_row.get("Status", ""),
                        to_int(clean_row.get("Started")),
                        to_int(clean_row.get("SF")),
                        passcode,
                    ),
                )

            elif table_name == "MonthlyRecords":
                cursor.execute(
                    """
                    INSERT INTO MonthlyRecords (
                        NUMBER, MONTH_, Year, ServiceYear, AttendcMidweekTotal, 
                        AttendcPublickTotal, NoMtgs1, NoMtgs2, ActivePublishers, passcode
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        to_int(clean_row.get("NUMBER")),
                        clean_row.get("MONTH_", ""),
                        to_int(clean_row.get("Year")),
                        to_int(clean_row.get("ServiceYear")),
                        to_int(clean_row.get("AttendcMidweekTotal")),
                        to_int(clean_row.get("AttendcPublickTotal")),
                        to_int(clean_row.get("NoMtgs1")),
                        to_int(clean_row.get("NoMtgs2")),
                        to_int(clean_row.get("ActivePublishers")),
                        passcode,
                    ),
                )

            else:  # RECORDS
                cursor.execute(
                    """
                    INSERT INTO RECORDS (IdPubs, NUMBER, Date_entered, HRS,BS, AUX, REMARKS, Note, MINISTRY, passcode)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        clean_row.get("IdPubs", ""),
                        to_int(clean_row.get("NUMBER")),
                        to_int(clean_row.get("Date_entered")),
                        to_float(clean_row.get("HRS")),
                        to_float(clean_row.get("BS")),
                        clean_row.get("AUX", ""),
                        clean_row.get("REMARKS", ""),
                        clean_row.get("Note", ""),
                        clean_row.get("MINISTRY", ""),
                        passcode,
                    ),
                )
            row_count += 1

        conn.commit()
        logger.info(
            f"Imported {row_count} rows into '{table_name}' for congregation passcode [{passcode}] and user [{username}]."
        )
        return f"{table_name} ({row_count} rows)"

    except Exception as e:
        conn.rollback()
        logger.error(
            f"Failed to process {filename} for passcode [{passcode}]: {str(e)}",
            exc_info=True,
        )
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import congregation CSV files into SQLite database.")
    parser.add_argument("file", help="Path to the CSV file to import")
    parser.add_argument("passcode", help="Passcode for the congregation")
    parser.add_argument("-u", "--username", default="", help="Username performing the import (optional)")
    parser.add_argument("-d", "--db", default=DEFAULT_DB, help="Path to SQLite database file (optional)")

    args = parser.parse_args()

    try:
        if not os.path.exists(args.file):
            print(f"Error: File '{args.file}' not found.")
            sys.exit(1)
            
        with open(args.file, "rb") as f:
            content_bytes = f.read()

        result = process_single_csv(
            filename=args.file,
            content_bytes=content_bytes,
            passcode=args.passcode,
            username=args.username,
            db_file=args.db
        )
        
        print(f"Successfully imported: {result}")

    except Exception as e:
        print(f"Import failed: {e}")
        sys.exit(1)


def import_csv_files(
    files_data: list[tuple[str, bytes]],
    passcode: str,
    username: str = "",
    db_file: str = DEFAULT_DB,
) -> list[str]:
    if not passcode or not passcode.strip():
        raise ValueError(
            "Passcode is required to segment congregation records."
        )

    results = []
    clean_passcode = passcode.strip()
    clean_username = username.strip()

    for filename, content_bytes in files_data:
        summary = process_single_csv(
            filename, content_bytes, clean_passcode, clean_username, db_file
        )
        results.append(summary)

    return results