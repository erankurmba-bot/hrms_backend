import os
import uuid
import pymssql
import pyodbc
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta

app = FastAPI()

# ================= JWT CONFIG =================
SECRET_KEY = "hrms_secret_key"
ALGORITHM = "HS256"

# ================= PASSWORD HASH =================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str):
    return pwd_context.verify(password, hashed)

def create_token(data: dict, expire_minutes: int = 60):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=expire_minutes)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# ================= DB CONNECTION =================
def get_connection():
    try:
        conn = pymssql.connect(
            server="db53111.public.databaseasp.net",
            port=1433,
            user="db53111",
            password="E=x57yC#o-4Z",
            database="db53111"
        )
        return conn

    except Exception as e:
        print("DB ERROR:", e)
        return None

# ================= FILE UPLOAD =================
uploads_path = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_path, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=uploads_path), name="uploads")

@app.post("/upload")
async def upload(
    request: Request,
    title: str = Form(...),
    className: str = Form(...),
    subject: str = Form(...),
    video: UploadFile = File(...)
):
    try:
        filename = f"{uuid.uuid4()}{os.path.splitext(video.filename)[1]}"
        file_path = os.path.join(uploads_path, filename)

        with open(file_path, "wb") as f:
            while chunk := await video.read(1024 * 1024):
                f.write(chunk)

        video_url = f"{request.base_url}uploads/{filename}"

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO TeacherVideos (Title, [Class], [Subject], VideoUrl) VALUES (?, ?, ?, ?)",
            (title, className, subject, video_url)
        )

        conn.commit()
        conn.close()

        return {"message": "Uploaded successfully", "url": video_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/uploadfile")
async def upload_file(
    request: Request,
    title: str = Form(...),
    className: str = Form(...),
    subject: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file selected")

        # uploads folder
        uploads_path = os.path.join(os.path.dirname(__file__), "uploads")
        os.makedirs(uploads_path, exist_ok=True)

        # unique filename
        ext = os.path.splitext(file.filename)[1]
        unique_name = f"{uuid.uuid4()}{ext}"

        file_path = os.path.join(uploads_path, unique_name)

        # save file
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)

        # file URL
        file_url = f"{request.base_url}uploads/{unique_name}"

        # file type
        content_type = file.content_type

        # save to DB
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO UploadedFiles
            (Title, Class, Subject, FileName, FileType, FileUrl)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            title,
            className,
            subject,
            unique_name,
            content_type,
            file_url
        ))

        conn.commit()
        conn.close()

        return {
            "message": "File uploaded successfully",
            "title": title,
            "class": className,
            "subject": subject,
            "fileName": unique_name,
            "fileType": content_type,
            "url": file_url
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================= VIDEOS =================
@app.get("/videos")
def get_videos():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
            SELECT 
                Id,
                Title,
                [Class] AS ClassName,
                [Subject],
                FileUrl,
                FileName,
                FileType,
                CreatedAt
            FROM dbo.UploadedFiles
            ORDER BY CreatedAt DESC
        """

        cursor.execute(query)

        rows = cursor.fetchall()

        columns = [column[0] for column in cursor.description]

        videos = [
            dict(zip(columns, row))
            for row in rows
        ]

        conn.close()

        return {
            "videos": videos
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
@app.get("/videos/class/{className}")
def get_videosByClass(className: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
            SELECT 
                Id,
                Title,
                [Class] AS ClassName,
                [Subject],
                FileUrl,
                FileName,
                FileType,
                CreatedAt
            FROM dbo.UploadedFiles
            WHERE [Class] = ?
            ORDER BY CreatedAt DESC
        """

        cursor.execute(query, (className,))

        rows = cursor.fetchall()

        columns = [column[0] for column in cursor.description]

        videos = [
            dict(zip(columns, row))
            for row in rows
        ]

        conn.close()

        return {
            "videos": videos
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
# ================= AUTH MODELS =================
class RegisterRequest(BaseModel):
    username: str
    password: str
    role_id: int
    className: str

class LoginRequest(BaseModel):
    username: str
    password: str

# ================= REGISTER =================
@app.post("/register")
def register(data: RegisterRequest):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB not connected")

    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO Users (Username, PasswordHash, ClassName) VALUES (?, ?, ?)",
        (data.username, data.password, data.className)
    )
    conn.commit()

    cursor.execute("SELECT Id FROM Users WHERE Username=?", (data.username,))
    user_id = cursor.fetchone()[0]

    cursor.execute(
        "INSERT INTO UserRoles (UserId, RoleId) VALUES (?, ?)",
        (user_id, data.role_id)
    )

    conn.commit()
    conn.close()

    return {"message": "User registered successfully"}
# ================= LOGIN =================
@app.post("/login")
def login(data: LoginRequest):
    conn = get_connection()

    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT Id, Username, PasswordHash, ClassName
        FROM Users
        WHERE Username=%s AND PasswordHash=%s
        """,
        (data.username, data.password)
    )

    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    user_id, username, password_hash, className = user

    cursor.execute(
        """
        SELECT r.Name
        FROM Roles r
        JOIN UserRoles ur ON r.Id = ur.RoleId
        WHERE ur.UserId=%s
        """,
        (user_id,)
    )

    roles = [r[0] for r in cursor.fetchall()]

    token = create_token({
        "user_id": user_id,
        "username": username,
        "roles": roles,
        "className": className
    })

    cursor.close()
    conn.close()

    return {
        "access_token": token,
        "token_type": "bearer",
        "roles": roles,
        "username": username,
        "className": className
    }

# ================= ROOT =================
@app.get("/")
def home():
    return {"message": "HRMS API running successfully"}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)