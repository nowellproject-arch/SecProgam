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
    "created_at" TIMESTAMPTZ NOT NULL,
    "payload" JSONB,
    "updated_at" TIMESTAMPTZ
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
    file: UploadFile | None = File(None)
):
    conn=None
    current_time=datetime.now(timezone.utc)
    clean_passcode=passcode.strip()
    clean_username=username.strip()
    clean_congregation=congregation.strip()

    try:
        conn=get_db_connection()
        conn.run(CREATE_SCHEMA_SQL)

        # 1. Check if passcode already exists
        existing_user=conn.run(
            'SELECT "passcode" FROM "MasterList" WHERE "passcode"=:passcode;',
            passcode=clean_passcode
        )

        if existing_user:
            raise HTTPException(
                status_code=409,
                detail="This code already exists. Please use Login."
            )

        # 2. Prepare CRB payload
        required_stores=["CongInfo","GROUPS","PUBLISHERS","MonthlyRecords","RECORDS"]

        if file is not None:
            content=await file.read()

            try:
                text=content.decode("cp1252")
                payload_data=json.loads(text)
            except UnicodeDecodeError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"CRB encoding error: {str(e)}"
                )
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"CRB JSON error at line {e.lineno}, column {e.colno}: {e.msg}"
                )

            # Make sure it is actually an object
            if not isinstance(payload_data,dict):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid CRB file format."
                )

            for store in required_stores:
                if store not in payload_data:
                    payload_data[store]=[]

        else:
            # No CRB supplied — create blank database payload
            payload_data={
                "CongInfo":[{
                    "passcode":clean_passcode,
                    "user":clean_username,
                    "Congregation":clean_congregation
                }],
                "GROUPS":[],
                "PUBLISHERS":[],
                "MonthlyRecords":[],
                "RECORDS":[]
            }

        # 3. Register NEW account in PostgreSQL
        conn.run(
            """
            INSERT INTO "MasterList"
            ("passcode","username","congregation","created_at")
            VALUES (:passcode,:username,:congregation,:created_at);
            """,
            passcode=clean_passcode,
            username=clean_username,
            congregation=clean_congregation,
            created_at=current_time
        )

        # 4. Save cloud backup
        conn.run(
            """
            UPDATE "MasterList"
            SET "payload"=CAST(:payload AS JSONB),
                "updated_at"=:updated_at
            WHERE "passcode"=:passcode;
            """,
            passcode=clean_passcode,
            payload=json.dumps(payload_data,default=str),
            updated_at=current_time
        )

        return {
            "status":"success",
            "action":"created",
            "message":"New account created successfully.",
            "data":payload_data
        }

    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        )
    finally:
        if conn:
            conn.close()

         