import base64
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, List, Union

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import BaseModel

from csv_importer import import_csv_files
from Sync import sync_router  # 🎯 Import sync router

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

# --- 3. REGISTER ROUTERS FIRST ---
app.include_router(sync_router, prefix="/api")
print("---> SYNC ROUTER LOADED SUCCESSFULLY <---")

# --- 4. MOUNT STATIC DIRECTORIES & TEMPLATES ---
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "Templates" if (BASE_DIR / "Templates").exists() else BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if TEMPLATES_DIR.exists():
    app.mount("/Templates", StaticFiles(directory=TEMPLATES_DIR), name="templates_static")
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
    conn = sqlite3.connect(BASE_DIR / "congReport.db") 
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT * FROM CongInfo WHERE user = ? AND passcode = ?", 
            (data.username, data.passcode)
        )
        user_record = cursor.fetchone()
        
        if not user_record:
            raise HTTPException(
                status_code=401, 
                detail="Invalid username or passcode."
            )
            
        return {
            "status": "success", 
            "message": "Login successful",
            "username": user_record["user"]
        }
        
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Database error: {str(e)}"
        )
    finally:
        conn.close()

@app.get("/api/reports")
async def api_reports(passcode: str):
    db_path = BASE_DIR / "congReport.db"
    if not db_path.exists():
        raise HTTPException(status_code=500, detail="Database file 'congReport.db' does not exist.")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row["name"] for row in cursor.fetchall() if row["name"] != "sqlite_sequence"]
        
        db_data = {}
        for table in tables:
            cursor.execute(f"SELECT * FROM {table}")
            rows = [dict(row) for row in cursor.fetchall()]
            db_data[table] = rows
            
        conn.close()
        return {"status": "success", "data": db_data}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/import-all-csv")
async def api_import_all_csv(
        files: List[UploadFile] = File(...),
        passcode: str = Form(...),
        username: str = Form("")
    ):
    """Receives CSV files from new-account.html and imports them into congReport.db."""
    try:
        clean_passcode = passcode.strip()
        clean_username = username.strip()
        
        if not clean_passcode:
            raise HTTPException(status_code=400, detail="Passcode is required.")

        files_data = []
        for file in files:
            content = await file.read()
            files_data.append((file.filename, content))
            
        db_path = BASE_DIR / "congReport.db"
        
        summaries = import_csv_files(
            files_data=files_data, 
            passcode=clean_passcode, 
            username=clean_username, 
            db_file=db_path
        )
        
        return {
            "status": "success", 
            "message": "Account created and all records successfully imported.",
            "summaries": summaries
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ CSV Import Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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