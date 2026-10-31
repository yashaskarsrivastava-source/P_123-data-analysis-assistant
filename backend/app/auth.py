import hashlib, hmac, os, secrets, smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from . import config
from .db import get_db
from .models import User

def hash_pw(pw: str) -> str:
    salt = os.urandom(16)
    return salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 120_000).hex()

def verify_pw(pw: str, stored: str) -> bool:
    salt, h = stored.split("$")
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120_000).hex(), h)

def new_password() -> str:
    return "".join(secrets.choice("abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(10))

def make_token(uid: int) -> str:
    return jwt.encode({"sub": str(uid), "exp": datetime.now(timezone.utc) + timedelta(days=7)}, config.SECRET_KEY, "HS256")

def current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    try:
        uid = int(jwt.decode((authorization or "").replace("Bearer ", ""), config.SECRET_KEY, ["HS256"])["sub"])
    except Exception:
        raise HTTPException(401, "Please log in again.")
    user = db.get(User, uid)
    if not user:
        raise HTTPException(401, "User not found.")
    return user

def send_password_email(to: str, name: str, pw: str) -> bool:
    if not config.SMTP_HOST:
        print(f"[DEV] SMTP not configured. Password for {to}: {pw}")
        return False
    try:
        m = EmailMessage()
        m["Subject"], m["From"], m["To"] = "Your P_123 Data Assistant password", config.SMTP_FROM, to
        m.set_content(f"Hi {name},\n\nYour password is: {pw}\n\nLog in and start asking questions about your data.\n")
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
            s.starttls()
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASS)
            s.send_message(m)
        return True
    except Exception as e:
        print("[MAIL ERROR]", e, "| password:", pw)
        return False
