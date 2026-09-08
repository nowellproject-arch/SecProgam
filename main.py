import base64
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import os
from pathlib import Path
import traceback
from typing import Any, Dict, Union
from urllib.parse import unquote, urlparse


from fastapi import Body, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pg8000.native
from pydantic import BaseModel
import traceback

# Import custom routers (using importer_router consistently)
from csv_importer import router as importer_router
from Sync import sync_router

from fastapi.responses import JSONResponse
from datetime import datetime




import asyncio
from fastapi import FastAPI
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

app = FastAPI()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)


DATABASE_SCHEMA = """
DATABASE: CongregationDB
DATABASE VERSION: 7

========================================
TABLE: CongInfo
========================================
Primary Key:
- passcode

Fields:
- passcode
- CongName
- Address
- Circuit
- ServiceYear
- Other congregation information fields

Purpose:
Stores congregation configuration and general congregation information.


========================================
TABLE: GROUPS
========================================
Primary Key:
- Group

Fields:
- Group
- Overseer
- Assistant
- Other group-related fields

Purpose:
Stores congregation field service groups.


========================================
TABLE: PUBLISHERS
========================================
Primary Key:
- IDPub

Fields:
- IDPub              : Unique Publisher ID
- FNAME              : First Name
- LName              : Last Name
- Gender
- Baptism
- BirthDate
- Group
- Status
- Elder
- MS
- Pioneer
- RegularPioneer
- AuxiliaryPioneer
- Other publisher information fields

Purpose:
Stores master publisher information.

Important:
PUBLISHERS.IDPub is linked to RECORDS.IdPubs.


========================================
TABLE: MonthlyRecords
========================================
Primary Key:
- NUMBER

Fields:
- NUMBER             : Unique Service Month Number
- Month
- Year
- Closed

Purpose:
Stores service month information.

Important:
MonthlyRecords.NUMBER is linked to RECORDS.NUMBER.


========================================
TABLE: RECORDS
========================================
Composite Primary Key:
- IdPubs
- NUMBER

Fields:
- IdPubs             : Publisher ID
- NUMBER             : Service Month Number
- Ministry
- HRs
- BS
- Remarks
- Date_Entered
- Other monthly report fields

Purpose:
Stores monthly publisher service reports.

Relationships:
- RECORDS.IdPubs = PUBLISHERS.IDPub
- RECORDS.NUMBER = MonthlyRecords.NUMBER


========================================
RELATIONSHIPS
========================================

PUBLISHERS
    IDPub
      |
      | 1-to-many
      |
RECORDS
    IdPubs


MonthlyRecords
    NUMBER
      |
      | 1-to-many
      |
RECORDS
    NUMBER


========================================
IMPORTANT FIELD MEANINGS
========================================

PUBLISHERS.IDPub
- Unique ID of a publisher.

PUBLISHERS.FNAME
- Publisher first name.

PUBLISHERS.LName
- Publisher last name.

PUBLISHERS.Baptism
- Baptism information.
- Empty or null Baptism may indicate an unbaptized publisher.

PUBLISHERS.Group
- Field service group assignment.

RECORDS.IdPubs
- Links monthly record to PUBLISHERS.IDPub.

RECORDS.NUMBER
- Service month identifier.

RECORDS.Ministry
- Monthly ministry/service status or activity.

RECORDS.HRs
- Reported ministry hours.

RECORDS.BS
- Bible studies.

RECORDS.Remarks
- Remarks or special report information.
- Example values may include "NEW UPB".

RECORDS.Date_Entered
- Date the monthly record was entered.

MonthlyRecords.NUMBER
- Unique month identifier.

MonthlyRecords.Closed
- Indicates whether a service month is closed.


========================================
QUERY RULES
========================================

1. Use ONLY tables and fields defined in this schema.
2. Never invent table names.
3. Never invent column names.
4. Use PUBLISHERS.IDPub = RECORDS.IdPubs when joining publisher records.
5. Use MonthlyRecords.NUMBER = RECORDS.NUMBER when joining month information.
6. For publisher identity queries, start with PUBLISHERS.
7. For monthly report queries, use RECORDS.
8. When both publisher information and monthly report information are required,
   join PUBLISHERS and RECORDS.
9. When month information is required, join MonthlyRecords.
10. NUMBER represents the service month identifier.
"""





# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# --- DATABASE HELPER FOR PG8000 ---
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

# --- 1. INITIALIZE FASTAPI APP (SINGLE INSTANCE) ---
app = FastAPI(title="congReport Congregation Management")



# --- 2. CORS MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(importer_router, prefix="/api")
app.include_router(sync_router, prefix="/api")

# --- 4. MOUNT STATIC DIRECTORIES & TEMPLATES ---
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = (
    BASE_DIR / "Templates"
    if (BASE_DIR / "Templates").exists()
    else BASE_DIR / "templates"
)
STATIC_DIR = BASE_DIR / "static"

if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if TEMPLATES_DIR.exists():
    app.mount(
        "/Templates",
        StaticFiles(directory=TEMPLATES_DIR),
        name="templates_static",
    )
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
else:
    templates = Jinja2Templates(directory=BASE_DIR)

# --- 5. SCHEMAS ---
class LoginRequest(BaseModel):
    username: str
    passcode: str

# -------------------------------------------------------------------
# HTML Page & Static View Routes
# -------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/current-month", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse(request=request, name="current_month_entry.html")

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/login.html", response_class=HTMLResponse)
async def serve_login(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/new-account.html", response_class=HTMLResponse)
async def serve_new_account(request: Request):
    return templates.TemplateResponse(request=request, name="new-account.html")

@app.get("/Templates/{form_name}", response_class=HTMLResponse)
async def get_template_file(request: Request, form_name: str):
    file_path = TEMPLATES_DIR / form_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Subform file '{form_name}' not found in {TEMPLATES_DIR}")
    return templates.TemplateResponse(request=request, name=form_name)

# -------------------------------------------------------------------
# Core API Endpoints
# -------------------------------------------------------------------

@app.post("/api/login")
async def login(data: LoginRequest):
    conn = None
    try:
        conn = get_db_connection()

        # Query MasterList joined with UserBackups
        query = """
            SELECT m."username", m."passcode", b."payload"
            FROM "MasterList" m
            LEFT JOIN "UserBackups" b ON m."passcode" = b."passcode"
            WHERE m."username" = :username AND m."passcode" = :passcode;
        """
        
        result = conn.run(
            query, 
            username=data.username.strip(), 
            passcode=data.passcode.strip()
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or passcode."
            )

        db_user, db_passcode, payload_raw = result[0]
        payload = json.loads(payload_raw) if isinstance(payload_raw, str) else (payload_raw or {})

        return {
            "status": "success",
            "message": "Login successful",
            "username": db_user,
            "passcode": db_passcode,
            "data": payload
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            conn.close()

@app.get("/api/reports")
@app.get("/api/restore")
async def api_reports(passcode: str):
    conn = None
    try:
        conn = get_db_connection()

        query = """
            SELECT m."username", m."congregation", b."payload", b."updated_at"
            FROM "MasterList" m
            LEFT JOIN "UserBackups" b ON m."passcode" = b."passcode"
            WHERE m."passcode" = :passcode;
        """
        result = conn.run(query, passcode=passcode.strip())

        if not result:
            raise HTTPException(status_code=404, detail="Account or passcode not found.")

        username, congregation, payload_raw, updated_at = result[0]

        if not payload_raw:
            raise HTTPException(status_code=404, detail="No backup snapshot found for this passcode.")

        payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw

        return {
            "status": "success",
            "user": {
                "username": username,
                "congregation": congregation,
                "last_backup": updated_at
            },
            "data": payload
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            conn.close()



# -------------------------------------------------------------------

def display_hours(record):
    value = record.get("HRS", "")
    if value is None or str(value).strip() in ("", "0", "0.0"):
        return ""
    return str(value)




@app.post("/api/generate-pdf")

def api_generate_pdf(data_payload: Union[dict, list] = Body(...)):
    """FastAPI endpoint to generate Google Slides PDF preview."""
    try:
        print("🚀 /api/generate-pdf CALLED")
        print("📦 Payload type:", type(data_payload))

        if not data_payload:
            raise HTTPException(
                status_code=400,
                detail="No data payload provided"
            )

        result = generate_publisher_record_pdf(data_payload)

        print("✅ PDF generation completed")
        return result

    except Exception as e:
        print("❌ PDF Generation Error:", str(e))
        print("❌ FULL TRACEBACK:")
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# -------------------------------------------------------------------
# Google Slides / Drive PDF Helper Functions
# -------------------------------------------------------------------

SCOPES = [
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/drive',
]

def get_oauth_credentials():
    token_json = os.getenv("GOOGLE_TOKEN_JSON")

    if token_json:
        print("✅ GOOGLE_TOKEN_JSON found")
        try:
            creds = Credentials.from_authorized_user_info(
                json.loads(token_json), SCOPES
            )
            if creds.expired and creds.refresh_token:
                print("🔄 Refreshing Google OAuth token...")
                creds.refresh(GoogleRequest())
            if not creds.valid:
                raise RuntimeError("GOOGLE_TOKEN_JSON credentials are invalid")
            print("✅ Google OAuth credentials ready")
            return creds
        except Exception as e:
            print(f"❌ GOOGLE_TOKEN_JSON authentication failed: {e}")
            raise

    print("⚠️ GOOGLE_TOKEN_JSON not found")

    if os.path.exists("token.json"):
        print("📄 Using local token.json")
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        if creds.expired and creds.refresh_token:
            print("🔄 Refreshing local Google OAuth token...")
            creds.refresh(GoogleRequest())
        if creds.valid:
            return creds

    print("🌐 Starting local Google OAuth...")
    flow = InstalledAppFlow.from_client_secrets_file(
        "credentials.json", SCOPES
    )
    creds = flow.run_local_server(port=0)
    with open("token.json", "w") as token:
        token.write(creds.to_json())
    return creds

def format_date(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(str(date_str).strip(), "%Y-%m-%d")
        return dt.strftime("%B %d, %Y").replace(" 0", " ")
    except Exception:
        return str(date_str)

def generate_publisher_record_pdf(data_payload):
    print("🔥🔥🔥 USING generate_publisher_record_pdf GOOGLE SLIDES VERSION")

    creds = get_oauth_credentials()
    slides_service = build('slides', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)
    template_id = "15rS-3_bi9kF4GM-iQdLt7m1GWcxuIr9p1l1y9xU5LOU"
    parents_id = "1XC_7zc1HiDmRzmduxVssFibf_e61JHIK"

    if not isinstance(data_payload, dict):
        raise ValueError("Expected two-service-year payload object")

    service_years = data_payload.get("serviceYears", {})
    publishers = data_payload.get("publishers", [])

    if not publishers:
        raise ValueError("No publishers provided")

    previous_info = service_years.get("previous", {})
    current_info = service_years.get("current", {})
    previous_year = int(previous_info.get("year", 0))
    current_year = int(current_info.get("year", 0))
    previous_numbers = previous_info.get("monthNumbers", [])
    current_numbers = current_info.get("monthNumbers", [])

    if len(previous_numbers) != 12:
        raise ValueError(f"Previous service year must contain 12 NUMBERs, got {len(previous_numbers)}")
    if len(current_numbers) != 12:
        raise ValueError(f"Current service year must contain 12 NUMBERs, got {len(current_numbers)}")

    print("========================================")
    print("📄 GENERATING TWO-SERVICE-YEAR PDF")
    print("========================================")
    print("Previous Service Year:", previous_year)
    print("Previous NUMBERs:", previous_numbers)
    print("Current Service Year:", current_year)
    print("Current NUMBERs:", current_numbers)
    print("Publishers:", len(publishers))

    # ---------------------------------------------------------
    # COPY TEMPLATE ONCE
    # ---------------------------------------------------------
    copy_body = {
        "name": f"MULTI_PRC_{current_year}",
        "parents": [parents_id]
    }
    copied_file = drive_service.files().copy(
        fileId=template_id,
        body=copy_body
    ).execute()
    temp_pres_id = copied_file["id"]
    print("📄 Temporary Slides ID:", temp_pres_id)

    try:
        # ---------------------------------------------------------
        # GET TEMPLATE SLIDE
        # ---------------------------------------------------------
        presentation = slides_service.presentations().get(
            presentationId=temp_pres_id
        ).execute()

        slides = presentation.get("slides", [])
        if not slides:
            raise ValueError("Template presentation contains no slides")

        template_slide_id = slides[0]["objectId"]
        print("📄 Template Slide ID:", template_slide_id)

        # ---------------------------------------------------------
        # REMOVE ANY EXTRA SLIDES FROM TEMPLATE
        # ---------------------------------------------------------
        cleanup_requests = []
        for slide in slides[1:]:
            cleanup_requests.append({
                "deleteObject": {
                    "objectId": slide["objectId"]
                }
            })

        if cleanup_requests:
            slides_service.presentations().batchUpdate(
                presentationId=temp_pres_id,
                body={"requests": cleanup_requests}
            ).execute()

        # ---------------------------------------------------------
        # HELPER FUNCTIONS
        # ---------------------------------------------------------
        def is_true(value):
            if value is None:
                return False
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return value != 0
            value = str(value).strip().upper()
            return value in {"1", "TRUE", "YES", "Y", "✓", "-1"}

        def check(value):
            return "✓" if is_true(value) else ""

        def safe_number(value):
            if value is None or value == "":
                return 0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0

        def get_record_by_number(records, number):
            target = str(number).strip()
            for record in records:
                record_number = str(record.get("NUMBER", "")).strip()
                if record_number == target:
                    return record
            return {}

        # ---------------------------------------------------------
        # GENERATE ONE SLIDE/PAGE FOR EACH PUBLISHER
        # ---------------------------------------------------------
        for publisher_index, pub in enumerate(publishers, start=1):
            pub_name = (
                pub.get("Fullname")
                or f"{pub.get('LName', '')}, {pub.get('FNAME', '')}".strip(", ")
                or "Unknown_Publisher"
            )

            print("----------------------------------------")
            print(f"👤 Publisher {publisher_index}/{len(publishers)}:", pub_name)
            print("🆔 IDPub:", pub.get("IDPub"))

            # -----------------------------------------------------
            # DUPLICATE THE ONE-PAGE TEMPLATE
            # -----------------------------------------------------
            duplicate_response = slides_service.presentations().batchUpdate(
                presentationId=temp_pres_id,
                body={
                    "requests": [
                        {
                            "duplicateObject": {
                                "objectId": template_slide_id
                            }
                        }
                    ]
                }
            ).execute()

            replies = duplicate_response.get("replies", [])
            if not replies:
                raise ValueError(f"Could not duplicate template slide for {pub_name}")

            new_slide_id = replies[0]["duplicateObject"]["objectId"]
            print("📄 New Slide ID:", new_slide_id)

            # -----------------------------------------------------
            # GET PUBLISHER RECORDS
            # -----------------------------------------------------
            previous_records = pub.get("previousYearRecords", []) or []
            current_records = pub.get("currentYearRecords", []) or []

            print(f"📋 {previous_year} records:", len(previous_records))
            print(f"📋 {current_year} records:", len(current_records))

            # -----------------------------------------------------
            # PLACEHOLDERS
            # TOP = PREVIOUS SERVICE YEAR
            # BOTTOM = CURRENT SERVICE YEAR
            # -----------------------------------------------------
            placeholders = {
                "{{Yeara}}": str(previous_year),
                "{{Yearb}}": str(current_year),
                "{{Name}}": pub.get("Fullname", ""),
                "{{PubID}}": str(pub.get("IDPub", "")),
                "{{BirthDate}}": format_date(pub.get("Birthdate", "")),
                "{{Baptism}}": format_date(pub.get("Baptism", "")),
                "{{RP}}": check(pub.get("RP")),
                "{{MS}}": check(pub.get("MS")),
                "{{SP}}": check(pub.get("SF")),
                "{{Elder}}": check(pub.get("Elder")),
                "{{Male}}": check(pub.get("Male")),
                "{{Female}}": check(pub.get("Female"))
            }

            # -----------------------------------------------------
            # MONTHLY RECORDS
            # -----------------------------------------------------
            total_hrs_previous = 0
            total_hrs_current = 0

            for i in range(12):
                idx = str(i + 1).zfill(2)
                previous_number = previous_numbers[i]
                current_number = current_numbers[i]

                previous_record = get_record_by_number(
                    previous_records,
                    previous_number
                )
                current_record = get_record_by_number(
                    current_records,
                    current_number
                )

                print(
                    f"Row {idx}: "
                    f"Previous NUMBER={previous_number}, "
                    f"Current NUMBER={current_number}"
                )

                if previous_record:
                    print(
                        f"   ↳ Previous found: "
                        f"MINISTRY={previous_record.get('MINISTRY')}, "
                        f"BS={previous_record.get('BS')}, "
                        f"AUX={previous_record.get('AUX')}, "
                        f"HRS={previous_record.get('HRS')}, "
                        f"REMARKS={previous_record.get('REMARKS')}"
                    )
                else:
                    print("   ↳ Previous record NOT FOUND")

                if current_record:
                    print(
                        f"   ↳ Current found: "
                        f"MINISTRY={current_record.get('MINISTRY')}, "
                        f"BS={current_record.get('BS')}, "
                        f"AUX={current_record.get('AUX')}, "
                        f"HRS={current_record.get('HRS')}, "
                        f"REMARKS={current_record.get('REMARKS')}"
                    )
                else:
                    print("   ↳ Current record NOT FOUND")

                # TOP = PREVIOUS SERVICE YEAR
                placeholders[f"{{{{Sa{idx}}}}}"] = check(
                    previous_record.get("MINISTRY")
                )
                placeholders[f"{{{{Ba{idx}}}}}"] = str(
                    previous_record.get("BS", "")
                )
                placeholders[f"{{{{Aa{idx}}}}}"] = check(
                    previous_record.get("AUX")
                )
                placeholders[f"{{{{Ha{idx}}}}}"] = display_hours(
                    previous_record
                )

                placeholders[f"{{{{Ra{idx}}}}}"] = str(previous_record.get("Note") or "")

                # BOTTOM = CURRENT SERVICE YEAR
                placeholders[f"{{{{Sb{idx}}}}}"] = check(
                    current_record.get("MINISTRY")
                )
                placeholders[f"{{{{Bb{idx}}}}}"] = str(
                    current_record.get("BS", "")
                )
                placeholders[f"{{{{Ab{idx}}}}}"] = check(
                    current_record.get("AUX")
                )
                placeholders[f"{{{{Hb{idx}}}}}"] = display_hours(
                    current_record
                )
                placeholders[f"{{{{Rb{idx}}}}}"] = str(current_record.get("Note") or "")

                total_hrs_previous += safe_number(
                    previous_record.get("HRS", 0)
                )
                total_hrs_current += safe_number(
                    current_record.get("HRS", 0)
                )

            # -----------------------------------------------------
            # TOTAL HOURS
            # -----------------------------------------------------
            placeholders["{{Tah}}"] = str(
                int(total_hrs_previous)
                if total_hrs_previous.is_integer()
                else total_hrs_previous
            )
            placeholders["{{Tbh}}"] = str(
                int(total_hrs_current)
                if total_hrs_current.is_integer()
                else total_hrs_current
            )

            print("📊 TOTAL HOURS")
            print(f"{previous_year}:", total_hrs_previous)
            print(f"{current_year}:", total_hrs_current)

            # -----------------------------------------------------
            # REPLACE ONLY ON THIS PUBLISHER'S SLIDE
            # -----------------------------------------------------
            requests = []

            for key, val in placeholders.items():
                requests.append({
                    "replaceAllText": {
                        "containsText": {
                            "text": key,
                            "matchCase": True
                        },
                        "replaceText": str(val),
                        "pageObjectIds": [new_slide_id]
                    }
                })

            print(
                "🔄 Placeholder replacement requests:",
                len(requests)
            )

            if requests:
                response = slides_service.presentations().batchUpdate(
                    presentationId=temp_pres_id,
                    body={"requests": requests}
                ).execute()

                print(
                    f"✅ Placeholders replaced for {pub_name}"
                )

        # ---------------------------------------------------------
        # DELETE ORIGINAL TEMPLATE SLIDE
        # ---------------------------------------------------------
        print("🗑️ Removing original template slide...")

        slides_service.presentations().batchUpdate(
            presentationId=temp_pres_id,
            body={
                "requests": [
                    {
                        "deleteObject": {
                            "objectId": template_slide_id
                        }
                    }
                ]
            }
        ).execute()

        print("✅ Original template slide removed")

        # ---------------------------------------------------------
        # EXPORT COMPLETE PRESENTATION TO ONE PDF
        # ---------------------------------------------------------
        print("📄 Exporting PDF...")

        pdf_request = drive_service.files().export_media(
            fileId=temp_pres_id,
            mimeType="application/pdf"
        )

        pdf_bytes = pdf_request.execute()
        b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    # ---------------------------------------------------------
    # FILE NAME
    # ---------------------------------------------------------
      
        batch_type = data_payload.get("batchType")

        if batch_type == "publishers":
            file_name = f"All_Publisher_PRC_{current_year}.pdf"
        elif batch_type == "unbaptized":
            file_name = f"All_Unbaptized_PRC_{current_year}.pdf"
        elif batch_type == "regular_pioneers":
            file_name = f"All_Regular_Pioneers_PRC_{current_year}.pdf"
        elif len(publishers) == 1:
            file_name = f"{pub_name}_PRC_{current_year}.pdf"
        else:
            file_name = f"MULTI_PRC_{current_year}.pdf"

            return {
                "success": True,
                "dataUrl": f"data:application/pdf;base64,{b64_pdf}",
                "fileName": file_name
            }

    finally:
        # ---------------------------------------------------------
        # DELETE TEMPORARY GOOGLE SLIDES FILE
        # ---------------------------------------------------------
        print("🗑️ Deleting temporary Google Slides file...")

        try:
            drive_service.files().delete(
                fileId=temp_pres_id
            ).execute()
            print("✅ Temporary Slides file deleted")
        except Exception as cleanup_error:
            print("⚠️ Could not delete temporary Slides file:", cleanup_error)


class BackupRequest(BaseModel):
    passcode: str
    payload: Dict[str, Any]

@app.post("/api/backup")
async def save_indexeddb_backup(data: BackupRequest):
    clean_passcode = data.passcode.strip()

    if not clean_passcode:
        raise HTTPException(
            status_code=400,
            detail="Passcode parameter is required."
        )
 
    conn = None

    try:
        conn = get_db_connection()

        current_time = datetime.now(
            timezone.utc
        ).astimezone(
            ZoneInfo("Asia/Manila")
        )

        formatted_time = current_time.strftime(
            "%Y-%m-%d %I:%M:%S%p"
        ).replace(
            " 0", " "
        ).lower()

        # 1. Delete existing backup for this passcode
        delete_query = """
            DELETE FROM "UserBackups"
            WHERE "passcode" = :passcode;
        """

        conn.run(
            delete_query,
            passcode=clean_passcode
        )

        print(
            f"🗑️ Deleted existing backup for "
            f"passcode: {clean_passcode}"
        )

        # 2. Insert the new backup
        insert_query = """
            INSERT INTO "UserBackups"
                ("passcode", "payload", "updated_at")
            VALUES
                (:passcode, CAST(:payload AS JSONB), :updated_at);
        """

        conn.run(
            insert_query,
            passcode=clean_passcode,
            payload=json.dumps(data.payload),
            updated_at=formatted_time
        )

        print(
            f"☁️ New backup saved for "
            f"passcode: {clean_passcode}"
        )

        return {
            "status": "success",
            "message": (
                "Existing backup replaced successfully."
            ),
            "updated_at": formatted_time
        }

    except Exception as e:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Database backup error: {str(e)}"
        )

    finally:
        if conn and hasattr(conn, "close"):
            conn.close()


@app.get("/api/backup-restore/{passcode}")
async def get_backup_payload(passcode: str):
    conn = None

    try:
        clean_passcode = passcode.strip()

        if not clean_passcode:
            raise HTTPException(
                status_code=400,
                detail="Passcode is required."
            )

        conn = get_db_connection()

        query = """
            SELECT payload, updated_at
            FROM "UserBackups"
            WHERE "passcode" = :passcode
            ORDER BY "updated_at" DESC
            LIMIT 1;
        """

        rows = conn.run(
            query,
            passcode=clean_passcode
        )

        if not rows:
            raise HTTPException(
                status_code=404,
                detail="No cloud backup found for this passcode."
            )

        return {
            "payload": rows[0][0],
            "updated_at": rows[0][1]
        }

    except HTTPException:
        raise

    except Exception as e:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Restore error: {str(e)}"
        )

    finally:
        if conn and hasattr(conn, "close"):
            conn.close()


# -------------------------------------------------------------------
# Backup export
# -------------------------------------------------------------------

@app.get("/api/export-backup")
def export_backup():

    try:
        # Congregation Information
        cong_info = []

        # Groups
        groups = []

        # Publishers
        publishers = []

        # Monthly Records
        monthly_records = []

        # Records
        records = []

        backup_data = {
            "CongInfo": cong_info,
            "GROUPS": groups,
            "PUBLISHERS": publishers,
            "MonthlyRecords": monthly_records,
            "RECORDS": records
        }

        return JSONResponse(
            content=backup_data,
            headers={
                "Content-Disposition":
                f'attachment; filename="Backup_{datetime.now().strftime("%Y%m%d")}.crb"'
            }
        )

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }



@app.post("/api/ai-query")
async def ai_query(data: dict):
    query = str(data.get("query", "")).strip()

    if not query:
        return {
            "answer": "Please enter a question.",
            "query_plan": {},
            "results": []
        }

    try:
        prompt = f"""
You are an AI Query Planner for the S-88-E Congregation Database.

You DO NOT have access to database rows.

You MUST NOT read, inspect, filter, or analyze actual publisher records.

Your only job is to convert the user's natural language request into a structured database query plan.

The backend or browser will execute your query plan against the local database.

DATABASE SCHEMA:
{DATABASE_SCHEMA}

USER REQUEST:
"{query}"

STRICT RULES:

1. NEVER invent database records.

2. NEVER answer questions using imaginary data.

3. NEVER request the entire database.

4. NEVER process database rows inside the AI prompt.

5. ONLY create a query plan.

6. Use ONLY table names and fields defined in DATABASE_SCHEMA.

7. If multiple tables are required, specify the joins.

8. Use filtering whenever possible.

9. Select only fields needed for the answer.

10. Use aggregation for:
   - count
   - total
   - sum
   - average
   - minimum
   - maximum

11. Use sorting when appropriate.

12. For questions about publishers, use PUBLISHERS.

13. For questions about monthly reports, use RECORDS.

14. For questions requiring both publisher identity and report data:
    JOIN PUBLISHERS.IDPub = RECORDS.IdPubs

15. For questions involving service months:
    JOIN RECORDS.NUMBER = MonthlyRecords.NUMBER

16. NEVER return actual database results.

17. The "results" array MUST always be [].

18. Return ONLY valid JSON.

19. Do not use Markdown.

20. Do not add explanations outside the JSON.

21. If the request is unclear, create the best possible query plan based
    only on the available DATABASE_SCHEMA.

22. Never invent a field just because it sounds logical.

23. If a requested field or information does not exist in DATABASE_SCHEMA,
    return an empty query_plan and explain this in "answer".

REQUIRED RESPONSE FORMAT:

{{
    "answer": "Short description of what will be searched",
    "query_plan": {{
        "tables": [],
        "joins": [],
        "select": [],
        "filters": [],
        "group_by": [],
        "aggregations": [],
        "order_by": [],
        "limit": null
    }},
    "results": []
}}

QUERY PLAN FORMAT DETAILS:

"tables":
[
    {{
        "name": "PUBLISHERS",
        "alias": "p"
    }}
]

"joins":
[
    {{
        "type": "INNER",
        "table": "RECORDS",
        "alias": "r",
        "condition": "p.IDPub = r.IdPubs"
    }}
]

"select":
[
    {{
        "field": "p.FNAME",
        "alias": "First Name"
    }},
    {{
        "field": "p.LName",
        "alias": "Last Name"
    }}
]

"filters":
[
    {{
        "field": "r.HRs",
        "operator": "=",
        "value": 0
    }}
]

"group_by":
[]

"aggregations":
[
    {{
        "function": "COUNT",
        "field": "p.IDPub",
        "alias": "Total"
    }}
]

"order_by":
[
    {{
        "field": "p.LName",
        "direction": "ASC"
    }}
]
"""

        response = None
        last_error = None

        # Try AI request up to 3 times
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )

                # Success - stop retrying
                break

            except Exception as retry_error:
                last_error = retry_error
                error_text = str(retry_error)

                print(
                    f"AI attempt {attempt + 1}/3 failed: {error_text}"
                )

                # Wait before retrying, except after final attempt
                if attempt < 2:
                    wait_seconds = 2 * (attempt + 1)
                    print(f"Retrying in {wait_seconds} seconds...")
                    await asyncio.sleep(wait_seconds)

        # All attempts failed
        if response is None:
            raise last_error

        # Parse AI JSON response
        query_result = json.loads(response.text)

        # Safety: AI must not return actual records
        query_result["results"] = []

        # Ensure required keys exist
        if "answer" not in query_result:
            query_result["answer"] = "Query plan created."

        if "query_plan" not in query_result:
            query_result["query_plan"] = {}

        return query_result

    except Exception as e:
        error_text = str(e)
        print(f"Gemini Error: {error_text}")

        if "503" in error_text or "UNAVAILABLE" in error_text:
            return {
                "answer": "The AI service is temporarily busy. Please try again in a few seconds.",
                "query_plan": {},
                "results": [],
                "error": "AI_SERVICE_BUSY"
            }

        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            return {
                "answer": "The AI request limit has been reached. Please wait a moment and try again.",
                "query_plan": {},
                "results": [],
                "error": "AI_RATE_LIMIT"
            }

        return {
            "answer": "Unable to process your request. Please try again.",
            "query_plan": {},
            "results": [],
            "error": "AI_ERROR"
        }






if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )