from __future__ import annotations

import os
import logging

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Any, Dict, Optional
import sqlite3
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta
from jarvis import JarvisLogger, JarvisSystem, JarvisConfig
from jarvis.protocols import Protocol
from jarvis.constants import DEFAULT_PORT
from jarvis.utils import detect_timezone
from fastapi.middleware.cors import CORSMiddleware

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
JWT_SECRET = os.getenv("JWT_SECRET", "secret")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", 60))


class ProtocolRunRequest(BaseModel):
    protocol: Optional[Dict[str, Any]] = None
    protocol_name: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None


app = FastAPI(title="Jarvis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React or Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JarvisRequest(BaseModel):
    command: str


class AuthRequest(BaseModel):
    email: str
    password: str


def create_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize the collaborative Jarvis system."""
    load_dotenv()
    level_name = os.getenv("JARVIS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    app.state.logger = JarvisLogger(log_level=level)
    config = JarvisConfig(
        ai_provider="openai",
        api_key=os.getenv("OPENAI_API_KEY"),
        calendar_api_url=os.getenv("CALENDAR_API_URL", "http://localhost:8080"),
        repo_path=os.getenv("REPO_PATH", "."),
        response_timeout=float(os.getenv("JARVIS_RESPONSE_TIMEOUT", 15.0)),
    )
    jarvis_system = JarvisSystem(config)
    await jarvis_system.initialize()
    app.state.jarvis_system = jarvis_system
    db_path = os.getenv("AUTH_DB_PATH", "auth.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password_hash TEXT)"
    )
    conn.commit()
    app.state.auth_db = conn


@app.on_event("shutdown")
async def shutdown_event() -> None:
    jarvis_system: JarvisSystem | None = getattr(app.state, "jarvis_system", None)
    if jarvis_system:
        await jarvis_system.shutdown()
    logger: JarvisLogger | None = getattr(app.state, "logger", None)
    if logger:
        logger.close()
    db: sqlite3.Connection | None = getattr(app.state, "auth_db", None)
    if db:
        db.close()


async def get_jarvis(request: Request) -> JarvisSystem:
    jarvis_system: JarvisSystem | None = getattr(
        request.app.state, "jarvis_system", None
    )
    if jarvis_system is None:
        raise HTTPException(status_code=500, detail="Jarvis system not initialized")
    return jarvis_system


@app.post("/jarvis")
async def jarvis(
    req: JarvisRequest,
    request: Request,
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """Execute a command using the agent network."""
    tz_name = detect_timezone(request)
    metadata = {
        "device": request.headers.get("X-Device"),
        "location": request.headers.get("X-Location"),
        "user": request.headers.get("X-User"),
        "source": request.headers.get("X-Source", "text"),
    }
    return await jarvis_system.process_request(req.command, tz_name, metadata)


@app.get("/protocols")
async def list_protocols(
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """Return all registered protocols with their details."""
    protocols = [
        p.to_dict() for p in jarvis_system.protocol_registry.protocols.values()
    ]
    return {"protocols": protocols}


@app.post("/protocols/run")
async def run_protocol(
    req: ProtocolRunRequest,
    jarvis_system: JarvisSystem = Depends(get_jarvis),
):
    """Run a protocol provided directly or by name."""
    if req.protocol is None and req.protocol_name is None:
        raise HTTPException(400, detail="protocol or protocol_name required")

    if req.protocol is not None:
        try:
            proto = Protocol.from_dict(req.protocol)
        except Exception as exc:
            raise HTTPException(400, detail=f"Invalid protocol: {exc}")
    else:
        proto = jarvis_system.protocol_registry.get(req.protocol_name)  # type: ignore[arg-type]
        if proto is None:
            raise HTTPException(404, detail="Protocol not found")

    results = await jarvis_system.protocol_executor.run_protocol(proto, req.arguments)
    return {"protocol": proto.name, "results": results}


@app.post("/signup")
async def signup(req: AuthRequest, request: Request):
    db: sqlite3.Connection = request.app.state.auth_db
    try:
        password_hash = pwd_context.hash(req.password)
        db.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (req.email, password_hash))
        db.commit()
    except sqlite3.IntegrityError:
        return JSONResponse({"error": "User already exists"}, status_code=400)
    token = create_token(req.email)
    return {"token": token}


@app.post("/login")
async def login(req: AuthRequest, request: Request):
    db: sqlite3.Connection = request.app.state.auth_db
    cur = db.execute("SELECT password_hash FROM users WHERE email = ?", (req.email,))
    row = cur.fetchone()
    if row is None or not pwd_context.verify(req.password, row[0]):
        return JSONResponse({"error": "Authentication failed"}, status_code=401)
    token = create_token(req.email)
    return {"token": token}


@app.get("/verify")
async def verify_token(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return JSONResponse({"error": "Authentication failed"}, status_code=401)
    email = decode_token(auth.split()[1])
    if not email:
        return JSONResponse({"error": "Authentication failed"}, status_code=401)
    return {"email": email}


def run():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=DEFAULT_PORT)


if __name__ == "__main__":
    run()
