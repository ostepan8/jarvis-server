from __future__ import annotations

import sqlite3
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from ..models import AuthRequest
from ..dependencies import get_auth_db
from ..auth import create_token, decode_token, hash_password, verify_password


router = APIRouter()


@router.post("/signup")
async def signup(req: AuthRequest, db: sqlite3.Connection = Depends(get_auth_db)):
    """Sign up a new user."""
    try:
        password_hash = hash_password(req.password)
        db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (req.email, password_hash),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return JSONResponse({"error": "User already exists"}, status_code=401)
    except Exception as e:
        # Better error handling for hashing issues
        return JSONResponse({"error": f"Signup failed: {str(e)}"}, status_code=500)

    token = create_token(req.email)
    return {"token": token}


@router.post("/login")
async def login(req: AuthRequest, db: sqlite3.Connection = Depends(get_auth_db)):
    """Log in a user."""
    cur = db.execute("SELECT password_hash FROM users WHERE email = ?", (req.email,))
    row = cur.fetchone()
    if row is None or not verify_password(req.password, row[0]):
        return JSONResponse({"error": "Authentication failed"}, status_code=401)
    token = create_token(req.email)
    return {"token": token}


@router.get("/verify")
async def verify_token(request: Request):
    """Verify a JWT token."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return JSONResponse({"error": "Authentication failed"}, status_code=401)
    email = decode_token(auth.split()[1])
    if not email:
        return JSONResponse({"error": "Authentication failed"}, status_code=401)
    return {"email": email}
