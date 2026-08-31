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

@app.post("/api/generate-pdf")
def api_generate_pdf(data_payload: Union[dict, list] = Body(...)):
    """FastAPI endpoint to generate Google Slides PDF preview."""
    try:
        if not data_payload:
            raise HTTPException(status_code=400, detail="No data payload provided")
            
        result = generate_publisher_record_pdf(data_payload)
        return result
    except Exception as e:
        print(f"❌ PDF Generation Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------
# Google Slides / Drive PDF Helper Functions
# -------------------------------------------------------------------

SCOPES = [
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/drive',
]

def get_oauth_credentials():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
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
    creds = get_oauth_credentials()

    slides_service = build('slides', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)
    
    template_id = "15rS-3_bi9kF4GM-iQdLt7m1GWcxuIr9p1l1y9xU5LOU"
    publishers = data_payload if isinstance(data_payload, list) else [data_payload]
    
    if not publishers:
        raise ValueError("No publishers provided")

    pub_name = publishers[0].get('publisher', {}).get('Name', 'Unknown_Publisher')

    copy_body = {
        'name': f"{pub_name}_PRC",
        'parents': ['1XC_7zc1HiDmRzmduxVssFibf_e61JHIK']
    }
    copied_file = drive_service.files().copy(fileId=template_id, body=copy_body).execute()
    temp_pres_id = copied_file['id']

    try:
        requests = []
        
        for pdata in publishers:
            pub = pdata.get('publisher', {})
            year = pdata.get('serviceYear', 2026)
            
            check = lambda v: "✓" if v in ["Yes", "✓", True, 1] else ""
            
            placeholders = {
                "{{YearA}}": str(year),
                "{{YearB}}": str(year - 1),
                "{{Name}}": pub.get("Name", ""),
                "{{PubID}}": str(pub.get("PubID", "")),
                "{{BirthDate}}": format_date(pub.get("Birthdate", "")),
                "{{Baptism}}": format_date(pub.get("Baptism", "")),
                "{{RP}}": check(pub.get("RP")),
                "{{MS}}": check(pub.get("MS")),
                "{{SP}}": check(pub.get("SP")),
                "{{Elder}}": check(pub.get("Elder")),
                "{{Male}}": check(pub.get("Male")),
                "{{Female}}": check(pub.get("Female"))
            }

            recsA = pdata.get("currentYear", {}).get("records", [])
            recsB = pdata.get("previousYear", {}).get("records", [])

            total_hrs_a = sum(float(r.get("HRS", 0) or 0) for r in recsA)
            total_hrs_b = sum(float(r.get("HRS", 0) or 0) for r in recsB)

            for i in range(12):
                a = recsA[i] if i < len(recsA) else {}
                b = recsB[i] if i < len(recsB) else {}
                idx = str(i + 1).zfill(2)

                placeholders[f"{{{{Sa{idx}}}}}"] = check(a.get("MINISTRY"))
                placeholders[f"{{{{Ba{idx}}}}}"] = str(a.get("BS", ""))
                placeholders[f"{{{{Aa{idx}}}}}"] = check(a.get("AUX"))
                placeholders[f"{{{{Ha{idx}}}}}"] = str(a.get("HRS", ""))
                placeholders[f"{{{{Ra{idx}}}}}"] = str(a.get("Note", ""))

                placeholders[f"{{{{Sb{idx}}}}}"] = check(b.get("MINISTRY"))
                placeholders[f"{{{{Bb{idx}}}}}"] = str(b.get("BS", ""))
                placeholders[f"{{{{Ab{idx}}}}}"] = check(b.get("AUX"))
                placeholders[f"{{{{Hb{idx}}}}}"] = str(b.get("HRS", ""))
                placeholders[f"{{{{Rb{idx}}}}}"] = str(b.get("Note", ""))

            placeholders["{{Tah}}"] = str(total_hrs_a)
            placeholders["{{Tbh}}"] = str(total_hrs_b)

            for key, val in placeholders.items():
                requests.append({
                    'replaceAllText': {
                        'containsText': {'text': key, 'matchCase': True},
                        'replaceText': val
                    }
                })

        if requests:
            slides_service.presentations().batchUpdate(
                presentationId=temp_pres_id, 
                body={'requests': requests}
            ).execute()

        pdf_request = drive_service.files().export_media(fileId=temp_pres_id, mimeType='application/pdf')
        pdf_bytes = pdf_request.execute()

        b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        file_name = f"{pub_name}_PRC_{publishers[0].get('serviceYear', 2026)}.pdf" if len(publishers) == 1 else "MULTI_PRC.pdf"

        return {
            "success": True,
            "dataUrl": f"data:application/pdf;base64,{b64_pdf}",
            "fileName": file_name
        }

    finally:
        drive_service.files().delete(fileId=temp_pres_id).execute()


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