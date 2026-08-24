import sqlite3
import time
import traceback
from pathlib import Path
from fastapi import APIRouter, HTTPException, Body

sync_router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "congReport.db"


def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(cursor):
    """Safely update existing tables with required sync tracking columns."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing_tables = {row[0] for row in cursor.fetchall()}

    target_tables = ["CongInfo", "GROUPS", "PUBLISHERS", "MonthlyRecords", "RECORDS"]

    for table in target_tables:
        if table not in existing_tables:
            continue

        cursor.execute(f"PRAGMA table_info({table})")
        cols = [column[1] for column in cursor.fetchall()]

        if "passcode" not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN passcode TEXT")
        if "updated_at" not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN updated_at INTEGER DEFAULT 0")
        if "is_deleted" not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN is_deleted INTEGER DEFAULT 0")


@sync_router.post("/sync")
async def sync_data(payload: dict = Body(...)):
    passcode = payload.get("passcode")
    last_sync = payload.get("last_sync", 0)
    changes = payload.get("changes", {})

    if not passcode:
        raise HTTPException(status_code=400, detail="Passcode required")

    conn = get_db_connection()
    cursor = conn.cursor()
    server_time = int(time.time() * 1000)

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        db_tables = [r[0] for r in cursor.fetchall()]

        ensure_schema(cursor)

        # --- PUSH: Process incoming records ---

        # 1. CongInfo (Match key: passcode) -> UPDATE ONLY
        if "CongInfo" in db_tables:
            for row in (changes.get("CongInfo") or changes.get("MONTH") or []):
                target_passcode = passcode or row.get("passcode")
                if target_passcode:
                    cursor.execute("""
                        UPDATE CongInfo 
                        SET Congregation = ?, 
                            CongNumber = ?, 
                            Address = ?, 
                            Province = ?, 
                            CBOE = ?, 
                            SO = ?, 
                            SEC = ?, 
                            User = ?, 
                            updated_at = ?, 
                            is_deleted = ?
                        WHERE passcode = ?
                    """, (
                        row.get("Congregation"), 
                        row.get("CongNumber"),
                        row.get("Address"), 
                        row.get("Province"), 
                        row.get("CBOE"), 
                        row.get("SO"), 
                        row.get("SEC"),
                        row.get("User"), 
                        row.get("updated_at", server_time), 
                        row.get("is_deleted", 0),
                        target_passcode
                    ))

        # 2. GROUPS (Match keys: passcode & Group_)
        if "GROUPS" in db_tables:
            for row in changes.get("GROUPS", []):
                group_val = row.get("Group") or row.get("Group_")
                
                # Attempt Update
                cursor.execute("""
                    UPDATE GROUPS
                    SET Overseer = ?, Assistant = ?, MeetingPlace = ?, Remarks = ?, updated_at = ?, is_deleted = ?
                    WHERE passcode = ? AND Group_ = ?
                """, (
                    row.get("Overseer"), row.get("Assistant"), row.get("MeetingPlace"),
                    row.get("Remarks"), row.get("updated_at", server_time),
                    row.get("is_deleted", 0), passcode, group_val
                ))
                
                # Insert if record was not found
                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO GROUPS (Group_, Overseer, Assistant, MeetingPlace, Remarks, passcode, updated_at, is_deleted)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        group_val, row.get("Overseer"), row.get("Assistant"),
                        row.get("MeetingPlace"), row.get("Remarks"), passcode,
                        row.get("updated_at", server_time), row.get("is_deleted", 0)
                    ))

        # 3. PUBLISHERS (Match keys: passcode & IDPub)
        if "PUBLISHERS" in db_tables:
            for row in changes.get("PUBLISHERS", []):
                id_pub = row.get("IDPub")
                
                cursor.execute("""
                    UPDATE PUBLISHERS
                    SET FNAME = ?, MName = ?, LName = ?, Nname = ?, Birthdate = ?, Male = ?, Female = ?,
                        Address = ?, TelCp = ?, Baptism = ?, Elder = ?, MS = ?, RP = ?, RpNumber = ?,
                        RpDateStarted = ?, GROUP_ = ?, Status = ?, Started = ?, updated_at = ?, is_deleted = ?
                    WHERE passcode = ? AND IDPub = ?
                """, (
                    row.get("FNAME"), row.get("MName"), row.get("LName"), row.get("Nname"),
                    row.get("Birthdate"), str(row.get("Male", "")), str(row.get("Female", "")),
                    row.get("Address"), row.get("TelCp"), row.get("Baptism"), str(row.get("Elder", "")),
                    str(row.get("MS", "")), str(row.get("RP", "")), row.get("RpNumber"),
                    row.get("RpDateStarted"), row.get("GROUP"), row.get("Status"), row.get("Started"),
                    row.get("updated_at", server_time), row.get("is_deleted", 0), passcode, id_pub
                ))

                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO PUBLISHERS (
                            IDPub, FNAME, MName, LName, Nname, Birthdate, Male, Female, Address, TelCp,
                            Baptism, Elder, MS, RP, RpNumber, RpDateStarted, GROUP_, Status, Started,
                            passcode, updated_at, is_deleted
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        id_pub, row.get("FNAME"), row.get("MName"), row.get("LName"), row.get("Nname"),
                        row.get("Birthdate"), str(row.get("Male", "")), str(row.get("Female", "")), row.get("Address"), row.get("TelCp"),
                        row.get("Baptism"), str(row.get("Elder", "")), str(row.get("MS", "")), str(row.get("RP", "")),
                        row.get("RpNumber"), row.get("RpDateStarted"), row.get("GROUP"), row.get("Status"), row.get("Started"),
                        passcode, row.get("updated_at", server_time), row.get("is_deleted", 0)
                    ))

        # 4. MonthlyRecords (Match keys: passcode & NUMBER)
        if "MonthlyRecords" in db_tables:
            for row in changes.get("MonthlyRecords", []):
                number_val = row.get("NUMBER")

                cursor.execute("""
                    UPDATE MonthlyRecords
                    SET MONTH_ = ?, Year = ?, ServiceYear = ?, AttendcMidweekTotal = ?, 
                        AttendcPublickTotal = ?, NoMtgs1 = ?, NoMtgs2 = ?, ActivePublishers = ?, 
                        updated_at = ?, is_deleted = ?
                    WHERE passcode = ? AND NUMBER = ?
                """, (
                    row.get("MONTH_"), row.get("Year"), row.get("ServiceYear"),
                    row.get("AttendcMidweekTotal"), row.get("AttendcPublickTotal"),
                    row.get("NoMtgs1"), row.get("NoMtgs2"), row.get("ActivePublishers"),
                    row.get("updated_at", server_time), row.get("is_deleted", 0),
                    passcode, number_val
                ))

                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO MonthlyRecords (
                            NUMBER, MONTH_, Year, ServiceYear, AttendcMidweekTotal, AttendcPublickTotal, 
                            NoMtgs1, NoMtgs2, ActivePublishers, passcode, updated_at, is_deleted
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        number_val, row.get("MONTH_"), row.get("Year"), row.get("ServiceYear"),
                        row.get("AttendcMidweekTotal"), row.get("AttendcPublickTotal"), row.get("NoMtgs1"), row.get("NoMtgs2"),
                        row.get("ActivePublishers"), passcode, row.get("updated_at", server_time), row.get("is_deleted", 0)
                    ))

        # 5. RECORDS (Match keys: passcode & NUMBER & IdPubs)
        if "RECORDS" in db_tables:
            for row in changes.get("RECORDS", []):
                number_val = row.get("NUMBER")
                id_pubs_val = row.get("IdPubs")

                cursor.execute("""
                    UPDATE RECORDS
                    SET Date_entered = ?, HRS = ?, AUX = ?, REMARKS = ?, Note = ?, 
                        updated_at = ?, is_deleted = ?
                    WHERE passcode = ? AND NUMBER = ? AND IdPubs = ?
                """, (
                    row.get("Date_entered"), row.get("HRS"), str(row.get("AUX", "")),
                    row.get("REMARKS"), row.get("Note"), row.get("updated_at", server_time),
                    row.get("is_deleted", 0), passcode, number_val, id_pubs_val
                ))

                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO RECORDS (
                            IdPubs, NUMBER, Date_entered, HRS, AUX, REMARKS, Note, passcode, updated_at, is_deleted
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        id_pubs_val, number_val, row.get("Date_entered"), row.get("HRS"),
                        str(row.get("AUX", "")), row.get("REMARKS"), row.get("Note"),
                        passcode, row.get("updated_at", server_time), row.get("is_deleted", 0)
                    ))

        conn.commit()

        # --- PULL: Fetch server changes ---
        updates = {}
        for tbl in ["CongInfo", "GROUPS", "PUBLISHERS", "MonthlyRecords", "RECORDS"]:
            if tbl in db_tables:
                cursor.execute(f"SELECT * FROM {tbl} WHERE passcode = ? AND updated_at > ?", (passcode, last_sync))
                updates[tbl] = [dict(r) for r in cursor.fetchall()]
            else:
                updates[tbl] = []

        return {"status": "success", "server_time": server_time, "updates": updates}

    except Exception as e:
        conn.rollback()
        print("\n=== SYNC ERROR TRACEBACK ===")
        traceback.print_exc()
        print("============================\n")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()