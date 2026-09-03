import base64
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import os
from pathlib import Path
import traceback
from typing import Any, Dict, Union
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
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
                placeholders[f"{{{{Ra{idx}}}}}"] = str(
                    previous_record.get("REMARKS")
                    or previous_record.get("Note")
                    or ""
                )

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
                placeholders[f"{{{{Rb{idx}}}}}"] = str(
                    current_record.get("REMARKS")
                    or current_record.get("Note")
                    or ""
                )

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
        if len(publishers) == 1:
            file_name = f"{pub_name}_PRC_{current_year}.pdf"
        else:
            file_name = f"MULTI_PRC_{current_year}.pdf"

        print("========================================")
        print("✅ PDF GENERATED SUCCESSFULLY")
        print("========================================")
        print("👥 Publishers:", len(publishers))
        print("📄 Pages:", len(publishers))
        print("📄 File name:", file_name)

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




if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )