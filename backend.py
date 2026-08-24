import logging
import os
import sqlite3
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from csv_importer import import_csv_files

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DB_FILE = "congReport.db"

app = FastAPI(title="Congregation Report API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Static Files Mounting (CSS & JS) ---
static_path = os.path.join(BASE_DIR, "static")
if not os.path.exists(static_path):
    os.makedirs(static_path, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_path), name="static")


# --- Data Models ---
class LoginRequest(BaseModel):
    username: str
    passcode: str


# --- Page & Sub-Form Serving Routes ---
@app.get("/")
async def read_index():
    index_path = os.path.join(BASE_DIR, "Templates", "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    raise HTTPException(status_code=404, detail="index.html not found in Templates folder")


@app.get("/login.html")
async def read_login():
    login_path = os.path.join(BASE_DIR, "Templates", "login.html")
    if os.path.exists(login_path):
        return FileResponse(
            login_path,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    raise HTTPException(status_code=404, detail="login.html not found in Templates folder")


@app.get("/new-account.html")
async def get_new_account():
    path = os.path.join("Templates", "new-account.html")
    if os.path.exists(path):
        return FileResponse(
            path,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/subform/{form_name}")
async def read_subform(form_name: str):
    """Dynamically serves HTML sub-forms (e.g., current_month_entry, publisher_record)."""
    if not form_name.endswith(".html"):
        form_name = f"{form_name}.html"
    
    subform_path = os.path.join(BASE_DIR, "Templates", form_name)
    if os.path.exists(subform_path):
        return FileResponse(
            subform_path,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    raise HTTPException(
        status_code=404, detail=f"Subform file '{form_name}' not found in Templates folder"
    )


# --- API Endpoints ---
@app.post("/api/login")
async def login_user(req: LoginRequest):
    """Validates if the passcode exists in the database for login."""
    clean_passcode = req.passcode.strip()
    if not clean_passcode:
        raise HTTPException(status_code=400, detail="Passcode is required.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        # Check if any data exists for this passcode in PUBLISHERS or RECORDS
        cursor.execute(
            "SELECT count(*) FROM PUBLISHERS WHERE passcode = ?", (clean_passcode,)
        )
        count = cursor.fetchone()[0]

        if count == 0:
            # Check RECORDS table as fallback
            cursor.execute(
                "SELECT count(*) FROM RECORDS WHERE passcode = ?", (clean_passcode,)
            )
            count = cursor.fetchone()[0]

        if count == 0:
            raise HTTPException(
                status_code=401,
                detail="Passcode not found. Please create an account first.",
            )

        return {
            "status": "success",
            "message": "Login successful",
            "passcode": clean_passcode,
            "username": req.username,
        }
    finally:
        conn.close()


@app.post("/api/import-all-csv")
async def import_all_csv(
    passcode: str = Form(...),
    username: str = Form(""),
    congregation: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    """Handles account setup and optional CSV migration."""
    clean_passcode = passcode.strip()
    clean_username = username.strip()

    if not clean_passcode:
        raise HTTPException(
            status_code=400, detail="Passcode parameter is required."
        )

    logger.info(
        f"Processing onboarding for user [{clean_username}], passcode [{clean_passcode}] ({len(files)} file(s))."
    )

    try:
        files_data = []
        for file in files:
            content = await file.read()
            files_data.append((file.filename, content))

        imported_tables = []
        if files_data:
            imported_tables = import_csv_files(
                files_data,
                passcode=clean_passcode,
                username=clean_username,
                db_file=DB_FILE,
            )

        return {
            "status": "success",
            "message": f"Successfully created account for [{clean_username}]. Imported: {', '.join(imported_tables) if imported_tables else 'None'}",
            "passcode": clean_passcode,
        }
    except Exception as e:
        logger.error(
            f"Import failure for passcode [{clean_passcode}]: {str(e)}"
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sync-save")
async def sync_save_records(payload: list[dict], passcode: str):
    """Synchronizes user updates back to sqlite filtered by congregation passcode."""
    clean_passcode = passcode.strip()
    if not clean_passcode:
        raise HTTPException(status_code=400, detail="Passcode is required.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        for row in payload:
            cursor.execute(
                """
                INSERT OR REPLACE INTO RECORDS (
                    IdPubs, NUMBER, Date_entered, HRS, AUX, REMARKS, Note, passcode
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    row.get("IdPubs", ""),
                    row.get("NUMBER", 0),
                    row.get("Date_entered", 0),
                    row.get("HRS", 0.0),
                    row.get("AUX", ""),
                    row.get("REMARKS", ""),
                    row.get("Note", ""),
                    clean_passcode,
                ),
            )
        conn.commit()
        return {
            "status": "success",
            "message": f"Successfully updated {len(payload)} record(s).",
        }
    except Exception as e:
        conn.rollback()
        logger.error(f"Sync failed for passcode [{clean_passcode}]: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/reports")
def get_reports(passcode: str):
    """Retrieves all stored records filtered strictly by congregation passcode."""
    clean_passcode = passcode.strip()
    if not clean_passcode:
        raise HTTPException(status_code=400, detail="Passcode is required.")

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        tables = [row[0] for row in cursor.fetchall()]

        all_data = {}
        for table in tables:
            cursor.execute(
                f"SELECT * FROM {table} WHERE passcode = ?", (clean_passcode,)
            )
            rows = [dict(row) for row in cursor.fetchall()]
            all_data[table] = rows

        return {"status": "success", "passcode": clean_passcode, "data": all_data}
    except Exception as e:
        logger.error(
            f"Failed to fetch reports for passcode [{clean_passcode}]: {str(e)}"
        )
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)