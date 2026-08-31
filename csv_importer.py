import csv
import io
import os
import json
import traceback
from datetime import datetime, timezone
from typing import List, Dict, Any
from urllib.parse import urlparse, unquote

import traceback
from datetime import datetime, timezone




from dotenv import load_dotenv
from fastapi import APIRouter, Form, File, UploadFile, HTTPException
import pg8000.native

load_dotenv()
router = APIRouter()
DATABASE_URL = os.getenv("DATABASE_URL")

CREATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS "MasterList" (
    "passcode" TEXT NOT NULL PRIMARY KEY,
    "username" TEXT NOT NULL,
    "congregation" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS "UserBackups" (
    "id" BIGSERIAL PRIMARY KEY,
    "passcode" TEXT NOT NULL,
    "payload" JSONB NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT fk_master
        FOREIGN KEY ("passcode")
        REFERENCES "MasterList"("passcode")
        ON DELETE CASCADE
);
"""

def get_db_connection():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL configuration missing.")
    parsed_url = urlparse(DATABASE_URL)
    return pg8000.native.Connection(
        user=unquote(parsed_url.username or ""),
        password=unquote(parsed_url.password or ""),
        host=parsed_url.hostname or "",
        port=parsed_url.port or 5432,
        database=parsed_url.path.lstrip("/"),
        ssl_context=True
    )

@router.post("/import-crb")
async def import_crb_file(
    username: str = Form(...),
    passcode: str = Form(...),
    congregation: str = Form(...),
    file: UploadFile = File(...)
):
    conn = None
    current_time = datetime.now(timezone.utc)
    clean_passcode = passcode.strip()
    clean_username = username.strip()

    try:
        conn = get_db_connection()
        conn.run(CREATE_SCHEMA_SQL)

        # 1. Credentials Lookup (Preserve cloud backup if user exists)
        existing_user = conn.run(
            'SELECT "passcode" FROM "MasterList" WHERE "passcode" = :passcode;',
            passcode=clean_passcode
        )

        if existing_user:
            return {
                "status": "success",
                "action": "login",
                "message": "User authenticated. Existing cloud backup retained.",
                "passcode": clean_passcode
            }

        # 2. Parse uploaded .crb JSON file
        content = await file.read()

        try:
             text = content.decode("cp1252")
             payload_data = json.loads(text)
        except UnicodeDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"CRB encoding error: {str(e)}"
            )
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"CRB JSON error at line {e.lineno}, "
                    f"column {e.colno}: {e.msg}"
                )
            )

        # Ensure required array keys exist
        required_stores = ["CongInfo", "GROUPS", "PUBLISHERS", "MonthlyRecords", "RECORDS"]
        for store in required_stores:
            if store not in payload_data:
                payload_data[store] = []

        # 3. Register Account into MasterList
        conn.run(
            """
            INSERT INTO "MasterList" ("passcode", "username", "congregation", "created_at")
            VALUES (:passcode, :username, :congregation, :created_at);
            """,
            passcode=clean_passcode,
            username=clean_username,
            congregation=congregation.strip(),
            created_at=current_time
        )

        # 4. Save payload into UserBackups
        conn.run(
            """
            INSERT INTO "UserBackups" ("passcode", "payload", "updated_at")
            VALUES (:passcode, CAST(:payload AS JSONB), :updated_at);
            """,
            passcode=clean_passcode,
            payload=json.dumps(payload_data, default=str),
            updated_at=current_time
        )

        return {
            "status": "success",
            "action": "created",
            "message": "New account created and .crb payload backed up.",
            "data": payload_data
        }

    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            conn.close()