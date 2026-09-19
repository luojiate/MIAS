from __future__ import annotations

import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import bcrypt
from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr, Field
from starlette.middleware.sessions import SessionMiddleware

from analyzer import analyze_image

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BACKEND_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB = os.getenv("MONGO_DB", "mias")
SESSION_SECRET = os.getenv("SESSION_SECRET", "mias-dev-session-secret-change-me")
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000").rstrip("/")

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:43173",
    "http://127.0.0.1:43173",
]
extra_origins = os.getenv("CORS_ORIGINS", "")
if extra_origins.strip():
    ALLOWED_ORIGINS.extend(origin.strip() for origin in extra_origins.split(",") if origin.strip())

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
}

mongo_client: AsyncIOMotorClient | None = None


def get_db() -> AsyncIOMotorDatabase:
    if mongo_client is None:
        raise HTTPException(status_code=503, detail="Database is not connected")
    return mongo_client[MONGO_DB]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global mongo_client
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    db = mongo_client[MONGO_DB]
    await db.users.create_index("email", unique=True)
    yield
    mongo_client.close()
    mongo_client = None


app = FastAPI(title="Medimage Analysis System", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=False,
    max_age=60 * 60 * 24 * 14,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterBody(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=1)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class CreateBody(BaseModel):
    number: str | int
    description: str
    userid: str | None = None
    image: str | None = None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def public_user(doc: dict[str, Any]) -> dict[str, str]:
    return {
        "ID": str(doc["_id"]),
        "name": doc.get("name", ""),
        "email": doc.get("email", ""),
    }


def require_userid(request: Request) -> str:
    userid = request.session.get("userid")
    if not userid:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(userid)


def serialize_analysis(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "image": doc.get("image", ""),
        "overlay": doc.get("overlay", ""),
        "inner_mask": doc.get("inner_mask", ""),
        "outer_mask": doc.get("outer_mask", ""),
        "number": doc.get("number", ""),
        "description": doc.get("description", ""),
        "userid": doc.get("userid", ""),
        "outer_fat": doc.get("outer_fat", 0),
        "inner_fat": doc.get("inner_fat", 0),
        "length": doc.get("length", 0),
        "width": doc.get("width", 0),
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/register")
async def register(body: RegisterBody):
    db = get_db()
    email = body.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    await db.users.insert_one(
        {
            "name": body.name.strip(),
            "email": email,
            "password": hash_password(body.password),
        }
    )
    return {"message": "User registered successfully"}


@app.post("/login")
async def login(request: Request, body: LoginBody):
    db = get_db()
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    request.session["userid"] = str(user["_id"])
    return {"message": "Login successful", "user": public_user(user)}


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"message": "Logged out"}


@app.post("/upload-image")
async def upload_image(request: Request, image: UploadFile = File(...)):
    userid = require_userid(request)
    content_type = (image.content_type or "").lower()
    suffix = ALLOWED_IMAGE_TYPES.get(content_type)
    if suffix is None:
        original = Path(image.filename or "").suffix.lower()
        suffix = original if original in {".jpg", ".jpeg", ".png", ".gif"} else None
    if suffix is None:
        raise HTTPException(status_code=400, detail="Image must be JPG, PNG, or GIF")
    if suffix == ".jpeg":
        suffix = ".jpg"

    filename = f"{uuid.uuid4().hex}{suffix}"
    dest = UPLOAD_DIR / filename
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    dest.write_bytes(payload)

    metrics = analyze_image(str(dest), out_dir=str(UPLOAD_DIR))
    image_url = f"{PUBLIC_URL}/uploads/{filename}"
    overlay_name = metrics.get("overlay_file")
    overlay_url = f"{PUBLIC_URL}/uploads/{overlay_name}" if overlay_name else None
    inner_mask_name = metrics.get("inner_mask_file")
    outer_mask_name = metrics.get("outer_mask_file")
    inner_mask_url = f"{PUBLIC_URL}/uploads/{inner_mask_name}" if inner_mask_name else None
    outer_mask_url = f"{PUBLIC_URL}/uploads/{outer_mask_name}" if outer_mask_name else None
    request.session["userid"] = userid
    request.session["uploaded_image"] = image_url
    request.session["overlay_image"] = overlay_url
    request.session["inner_mask"] = inner_mask_url
    request.session["outer_mask"] = outer_mask_url
    request.session["outerFat"] = metrics["outerFat"]
    request.session["innerFat"] = metrics["innerFat"]
    request.session["length"] = metrics["length"]
    request.session["width"] = metrics["width"]
    return {
        "message": "Image uploaded",
        "image": image_url,
        "url": image_url,
        "overlay": overlay_url,
        "innerMask": inner_mask_url,
        "outerMask": outer_mask_url,
        "outerFat": metrics["outerFat"],
        "innerFat": metrics["innerFat"],
        "length": metrics["length"],
        "width": metrics["width"],
    }


@app.post("/create")
async def create_analysis(request: Request, body: CreateBody):
    userid = require_userid(request)
    if body.userid and body.userid != userid:
        raise HTTPException(status_code=403, detail="userid does not match the signed-in user")
    image_url = body.image or request.session.get("uploaded_image")
    if not image_url:
        raise HTTPException(status_code=400, detail="No uploaded image found. Upload an image first.")

    doc = {
        "image": image_url,
        "overlay": request.session.get("overlay_image", ""),
        "inner_mask": request.session.get("inner_mask", ""),
        "outer_mask": request.session.get("outer_mask", ""),
        "number": body.number,
        "description": body.description,
        "userid": userid,
        "outer_fat": request.session.get("outerFat", 0),
        "inner_fat": request.session.get("innerFat", 0),
        "length": request.session.get("length", 0),
        "width": request.session.get("width", 0),
    }
    db = get_db()
    result = await db.analyses.insert_one(doc)
    created = await db.analyses.find_one({"_id": result.inserted_id})
    return {"message": "Analysis created", **serialize_analysis(created or {**doc, "_id": result.inserted_id})}


@app.get("/personal")
async def personal(request: Request):
    userid = require_userid(request)
    db = get_db()
    cursor = db.analyses.find({"userid": userid}).sort("_id", -1)
    return [serialize_analysis(doc) async for doc in cursor]


@app.delete("/delete/{analysis_id}")
async def delete_analysis(request: Request, analysis_id: str):
    userid = require_userid(request)
    try:
        oid = ObjectId(analysis_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail="Invalid analysis id") from exc
    db = get_db()
    doc = await db.analyses.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if str(doc.get("userid")) != userid:
        raise HTTPException(status_code=403, detail="You can only delete your own analyses")
    await db.analyses.delete_one({"_id": oid})
    image_url = str(doc.get("image") or "")
    match = re.search(r"/uploads/([^/?#]+)$", image_url)
    if match:
        file_path = UPLOAD_DIR / match.group(1)
        if file_path.is_file() and file_path.resolve().parent == UPLOAD_DIR.resolve():
            file_path.unlink(missing_ok=True)
    return {"message": "Analysis deleted"}


app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
