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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from analyzer import analyze_image

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _split_origins(value: str) -> list[str]:
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


BACKEND_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BACKEND_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB = os.getenv("MONGO_DB", "mias")
SESSION_SECRET = os.getenv("SESSION_SECRET", "mias-dev-session-secret-change-me")
PUBLIC_URL = (
    os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL") or "http://localhost:8000"
).rstrip("/")

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:43173",
    "http://127.0.0.1:43173",
]
EXTRA_ORIGINS = _split_origins(os.getenv("CORS_ORIGINS", ""))
if PUBLIC_URL.startswith("http"):
    ALLOWED_ORIGINS.append(PUBLIC_URL)
ALLOWED_ORIGINS = _dedupe([*ALLOWED_ORIGINS, *EXTRA_ORIGINS])

# Same-origin (FastAPI serves the SPA) → Lax. Cross-site Vercel → Render needs None+Secure.
CROSS_SITE = bool(EXTRA_ORIGINS)
IS_HTTPS = PUBLIC_URL.startswith("https://") or _env_bool("RENDER", False)
SESSION_SAMESITE = os.getenv("SESSION_SAMESITE", "none" if CROSS_SITE else "lax").lower()
if SESSION_SAMESITE not in {"lax", "strict", "none"}:
    SESSION_SAMESITE = "lax"
SESSION_HTTPS_ONLY = _env_bool(
    "SESSION_HTTPS_ONLY",
    default=(SESSION_SAMESITE == "none") or IS_HTTPS,
)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
}
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif"}
MAX_BATCH_FILES = 8
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

mongo_client: AsyncIOMotorClient | None = None


def get_db() -> AsyncIOMotorDatabase:
    if mongo_client is None:
        raise HTTPException(status_code=503, detail="Database is not connected")
    return mongo_client[MONGO_DB]


def _resolve_spa_dir() -> Path | None:
    env = os.getenv("SPA_DIR", "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            BACKEND_DIR / "frontend" / "dist",
            BACKEND_DIR.parent / "frontend" / "dist",
        ]
    )
    for path in candidates:
        if (path / "index.html").is_file():
            return path.resolve()
    return None


SPA_DIR = _resolve_spa_dir()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global mongo_client
    mongo_client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=20000)
    db = mongo_client[MONGO_DB]
    await db.users.create_index("email", unique=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from vision.infer import ensure_sessions

        ensure_sessions()
        print("[mias] ONNX sessions ready", flush=True)
    except Exception as exc:
        print(f"[mias] ONNX warmup skipped: {exc!r}", flush=True)
    print(
        f"[mias] spa={SPA_DIR} same_site={SESSION_SAMESITE} "
        f"https_only={SESSION_HTTPS_ONLY} cors={ALLOWED_ORIGINS}",
        flush=True,
    )
    yield
    mongo_client.close()
    mongo_client = None


app = FastAPI(title="Medimage Analysis System", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site=SESSION_SAMESITE,
    https_only=SESSION_HTTPS_ONLY,
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
    overlay: str | None = None
    inner_mask: str | None = None
    outer_mask: str | None = None
    outer_fat: float | int | None = None
    inner_fat: float | int | None = None
    length: float | int | None = None
    width: float | int | None = None


class CreateBatchItem(BaseModel):
    number: str | int
    description: str
    image: str
    overlay: str | None = None
    inner_mask: str | None = None
    outer_mask: str | None = None
    outer_fat: float | int | None = None
    inner_fat: float | int | None = None
    length: float | int | None = None
    width: float | int | None = None


class CreateBatchBody(BaseModel):
    userid: str | None = None
    items: list[CreateBatchItem] = Field(default_factory=list)


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


def public_base_url(request: Request) -> str:
    """Absolute origin for stored upload URLs (PUBLIC_URL, Render URL, or request host)."""
    configured = os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL")
    if configured:
        base = configured.rstrip("/")
        if "localhost" not in base and "127.0.0.1" not in base:
            return base
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host:
        return f"{proto}://{host}".rstrip("/")
    return PUBLIC_URL


def _wants_html(request: Request) -> bool:
    dest = request.headers.get("sec-fetch-dest", "").lower()
    if dest == "document":
        return True
    return "text/html" in request.headers.get("accept", "").lower()


def spa_index() -> FileResponse:
    assert SPA_DIR is not None
    return FileResponse(SPA_DIR / "index.html")


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


def image_suffix(content_type: str, filename: str) -> str | None:
    suffix = ALLOWED_IMAGE_TYPES.get((content_type or "").lower())
    if suffix is None:
        original = Path(filename or "").suffix.lower()
        suffix = original if original in ALLOWED_IMAGE_SUFFIXES else None
    if suffix == ".jpeg":
        suffix = ".jpg"
    return suffix


def upload_urls(origin: str, filename: str, metrics: dict[str, Any]) -> dict[str, Any]:
    image_url = f"{origin}/uploads/{filename}"
    overlay_name = metrics.get("overlay_file")
    inner_mask_name = metrics.get("inner_mask_file")
    outer_mask_name = metrics.get("outer_mask_file")
    return {
        "message": "Image uploaded",
        "image": image_url,
        "url": image_url,
        "overlay": f"{origin}/uploads/{overlay_name}" if overlay_name else None,
        "innerMask": f"{origin}/uploads/{inner_mask_name}" if inner_mask_name else None,
        "outerMask": f"{origin}/uploads/{outer_mask_name}" if outer_mask_name else None,
        "outerFat": metrics["outerFat"],
        "innerFat": metrics["innerFat"],
        "length": metrics["length"],
        "width": metrics["width"],
    }


def save_and_analyze(payload: bytes, suffix: str, origin: str) -> dict[str, Any]:
    filename = f"{uuid.uuid4().hex}{suffix}"
    dest = UPLOAD_DIR / filename
    dest.write_bytes(payload)
    metrics = analyze_image(str(dest), out_dir=str(UPLOAD_DIR))
    return upload_urls(origin, filename, metrics)


def store_last_upload(request: Request, userid: str, result: dict[str, Any]) -> None:
    request.session["userid"] = userid
    request.session["uploaded_image"] = result.get("image")
    request.session["overlay_image"] = result.get("overlay")
    request.session["inner_mask"] = result.get("innerMask")
    request.session["outer_mask"] = result.get("outerMask")
    request.session["outerFat"] = result.get("outerFat", 0)
    request.session["innerFat"] = result.get("innerFat", 0)
    request.session["length"] = result.get("length", 0)
    request.session["width"] = result.get("width", 0)


def _session_or_body(body_value: Any, session_key: str, request: Request, default: Any = "") -> Any:
    if body_value is not None:
        return body_value
    value = request.session.get(session_key, default)
    return default if value is None else value


def analysis_document(
    userid: str,
    number: str | int,
    description: str,
    image_url: str,
    overlay: Any = "",
    inner_mask: Any = "",
    outer_mask: Any = "",
    outer_fat: Any = 0,
    inner_fat: Any = 0,
    length: Any = 0,
    width: Any = 0,
) -> dict[str, Any]:
    return {
        "image": image_url,
        "overlay": overlay or "",
        "inner_mask": inner_mask or "",
        "outer_mask": outer_mask or "",
        "number": number,
        "description": description,
        "userid": userid,
        "outer_fat": 0 if outer_fat is None else outer_fat,
        "inner_fat": 0 if inner_fat is None else inner_fat,
        "length": 0 if length is None else length,
        "width": 0 if width is None else width,
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
    suffix = image_suffix(image.content_type or "", image.filename or "")
    if suffix is None:
        raise HTTPException(status_code=400, detail="Image must be JPG, PNG, or GIF")

    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds the 10 MB size limit")

    result = save_and_analyze(payload, suffix, public_base_url(request))
    store_last_upload(request, userid, result)
    return result


@app.post("/upload-images")
async def upload_images(request: Request, images: list[UploadFile] | None = File(default=None)):
    userid = require_userid(request)
    files = images or []
    if not files:
        raise HTTPException(status_code=400, detail="請至少選擇一張影像。")
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"一次最多上傳 {MAX_BATCH_FILES} 張影像。")

    origin = public_base_url(request)
    results: list[dict[str, Any]] = []
    last_ok: dict[str, Any] | None = None

    for index, image in enumerate(files):
        filename = image.filename or f"image-{index + 1}"
        suffix = image_suffix(image.content_type or "", filename)
        if suffix is None:
            results.append(
                {
                    "index": index,
                    "filename": filename,
                    "success": False,
                    "error": "影像須為 JPG、PNG 或 GIF。",
                }
            )
            continue
        payload = await image.read()
        if not payload:
            results.append(
                {
                    "index": index,
                    "filename": filename,
                    "success": False,
                    "error": "上傳的檔案是空的。",
                }
            )
            continue
        if len(payload) > MAX_UPLOAD_BYTES:
            results.append(
                {
                    "index": index,
                    "filename": filename,
                    "success": False,
                    "error": "檔案超過 10 MB 上限。",
                }
            )
            continue
        try:
            item = save_and_analyze(payload, suffix, origin)
            last_ok = item
            results.append({"index": index, "filename": filename, "success": True, "error": None, **item})
        except Exception:
            results.append(
                {
                    "index": index,
                    "filename": filename,
                    "success": False,
                    "error": "分析失敗，請再試一次。",
                }
            )

    if last_ok is not None:
        store_last_upload(request, userid, last_ok)

    succeeded = sum(1 for item in results if item.get("success"))
    return {
        "message": "批次分析完成",
        "results": results,
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
    }


@app.post("/create")
async def create_analysis(request: Request, body: CreateBody):
    userid = require_userid(request)
    if body.userid and body.userid != userid:
        raise HTTPException(status_code=403, detail="userid does not match the signed-in user")
    image_url = body.image or request.session.get("uploaded_image")
    if not image_url:
        raise HTTPException(status_code=400, detail="No uploaded image found. Upload an image first.")

    doc = analysis_document(
        userid=userid,
        number=body.number,
        description=body.description,
        image_url=str(image_url),
        overlay=_session_or_body(body.overlay, "overlay_image", request),
        inner_mask=_session_or_body(body.inner_mask, "inner_mask", request),
        outer_mask=_session_or_body(body.outer_mask, "outer_mask", request),
        outer_fat=_session_or_body(body.outer_fat, "outerFat", request, 0),
        inner_fat=_session_or_body(body.inner_fat, "innerFat", request, 0),
        length=_session_or_body(body.length, "length", request, 0),
        width=_session_or_body(body.width, "width", request, 0),
    )
    db = get_db()
    result = await db.analyses.insert_one(doc)
    created = await db.analyses.find_one({"_id": result.inserted_id})
    return {"message": "Analysis created", **serialize_analysis(created or {**doc, "_id": result.inserted_id})}


@app.post("/create-batch")
async def create_batch(request: Request, body: CreateBatchBody):
    userid = require_userid(request)
    if body.userid and body.userid != userid:
        raise HTTPException(status_code=403, detail="userid does not match the signed-in user")
    if not body.items:
        raise HTTPException(status_code=400, detail="請至少選擇一筆要儲存的分析。")
    if len(body.items) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"一次最多儲存 {MAX_BATCH_FILES} 筆分析。")
    for item in body.items:
        if not (item.image or "").strip():
            raise HTTPException(status_code=400, detail="每筆分析都需要影像網址。")

    docs = [
        analysis_document(
            userid=userid,
            number=item.number,
            description=item.description,
            image_url=item.image.strip(),
            overlay=item.overlay,
            inner_mask=item.inner_mask,
            outer_mask=item.outer_mask,
            outer_fat=item.outer_fat,
            inner_fat=item.inner_fat,
            length=item.length,
            width=item.width,
        )
        for item in body.items
    ]
    db = get_db()
    result = await db.analyses.insert_many(docs)
    created = [
        serialize_analysis({**doc, "_id": oid})
        for doc, oid in zip(docs, result.inserted_ids, strict=True)
    ]
    return {"message": f"已儲存 {len(created)} 筆分析", "items": created}


@app.get("/personal")
async def personal(request: Request):
    # Browser refresh of the SPA route must not hit the JSON API (same path).
    if SPA_DIR is not None and _wants_html(request):
        return spa_index()
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


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
if SPA_DIR is not None:
    app.mount("/", SpaStaticFiles(directory=str(SPA_DIR), html=True), name="spa")
