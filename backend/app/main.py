import shutil, uuid
from pathlib import Path
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from . import config
from .auth import current_user, hash_pw, make_token, new_password, send_password_email, verify_pw
from .db import Base, engine, get_db
from .domain.data_analysis import AnalysisError
from .engines.schema_profiler import load_dataframe, profile, validate_schema
from .models import Conversation, Dataset, Message, User
from .services.analysis_service import run_question

Path(config.BASE / "data").mkdir(exist_ok=True)
config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(engine)
app = FastAPI(title="P_123 Conversational Data Analysis Assistant")

class SignupIn(BaseModel): email: EmailStr; name: str = Field(min_length=1, max_length=80)
class LoginIn(BaseModel): email: EmailStr; password: str
class ResetIn(BaseModel): email: EmailStr
class ConvIn(BaseModel): dataset_id: int
class AskIn(BaseModel): question: str = Field(min_length=1, max_length=500); language: str = "en"

def user_out(u): return {"id": u.id, "email": u.email, "name": u.name}
def ds_out(d): return {"id": d.id, "name": d.name, "rows": d.profile["rows"], "profile": d.profile}

def _issue_password(db, user, name):
    pw = new_password(); user.password_hash = hash_pw(pw); db.commit()
    sent = send_password_email(user.email, name, pw)
    return {"email_sent": sent, "message": f"Password sent to {user.email}." if sent else "Email is not configured on the server (dev mode).",
            "dev_password": pw if (not sent and config.DEV_SHOW_PASSWORD) else None}

# ---------- auth ----------
@app.post("/api/auth/signup")
def signup(b: SignupIn, db: Session = Depends(get_db)):
    email = b.email.lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "This email is already registered. Use 'Forgot password' to get a new password.")
    u = User(email=email, name=b.name.strip(), password_hash="x"); db.add(u); db.commit()
    return _issue_password(db, u, u.name)

@app.post("/api/auth/reset")
def reset(b: ResetIn, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(email=b.email.lower()).first()
    if not u: raise HTTPException(404, "No account with this email.")
    return _issue_password(db, u, u.name)

@app.post("/api/auth/login")
def login(b: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(email=b.email.lower()).first()
    if not u or not verify_pw(b.password, u.password_hash): raise HTTPException(401, "Wrong email or password.")
    return {"token": make_token(u.id), "user": user_out(u)}

@app.get("/api/me")
def me(u: User = Depends(current_user)): return user_out(u)

# ---------- datasets ----------
def _store(db, u, src: Path, name: str) -> Dataset:
    udir = config.UPLOAD_DIR / str(u.id); udir.mkdir(parents=True, exist_ok=True)
    dest = udir / f"{uuid.uuid4().hex[:8]}_{name}"; shutil.copy(src, dest)
    try:
        df = load_dataframe(str(dest)); validate_schema(df)
    except AnalysisError as e:
        dest.unlink(missing_ok=True); raise HTTPException(400, e.message)
    d = Dataset(user_id=u.id, name=name, path=str(dest), profile=profile(df)); db.add(d); db.commit()
    return d

@app.get("/api/datasets")
def datasets(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [ds_out(d) for d in db.query(Dataset).filter_by(user_id=u.id).order_by(Dataset.id.desc())]

@app.post("/api/datasets")
def upload(file: UploadFile = File(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    name = Path(file.filename or "data").name
    if not name.lower().endswith((".csv", ".xlsx")): raise HTTPException(400, "Only .csv and .xlsx files are supported.")
    tmp = config.UPLOAD_DIR / f"tmp_{uuid.uuid4().hex}"
    with open(tmp, "wb") as f: shutil.copyfileobj(file.file, f)
    try:
        if tmp.stat().st_size > 20 * 1024 * 1024: raise HTTPException(400, "File is larger than 20 MB.")
        return ds_out(_store(db, u, tmp, name))
    finally: tmp.unlink(missing_ok=True)

@app.get("/api/samples")
def samples(u: User = Depends(current_user)): return sorted(p.name for p in config.SAMPLE_DIR.glob("*.csv"))

@app.post("/api/datasets/sample/{name}")
def use_sample(name: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = config.SAMPLE_DIR / Path(name).name
    if not p.exists(): raise HTTPException(404, "Sample not found.")
    return ds_out(_store(db, u, p, p.name))

@app.delete("/api/datasets/{did}")
def delete_dataset(did: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    d = db.query(Dataset).filter_by(id=did, user_id=u.id).first()
    if not d: raise HTTPException(404, "Dataset not found.")
    for c in db.query(Conversation).filter_by(dataset_id=did).all():
        db.query(Message).filter_by(conversation_id=c.id).delete(); db.delete(c)
    Path(d.path).unlink(missing_ok=True); db.delete(d); db.commit(); return {"ok": True}

# ---------- conversations ----------
def _conv(db, u, cid):
    c = db.query(Conversation).filter_by(id=cid, user_id=u.id).first()
    if not c: raise HTTPException(404, "Chat not found.")
    return c
def msg_out(m): return {"id": m.id, "role": m.role, "content": m.content, "result": m.result}

@app.get("/api/conversations")
def conversations(u: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": c.id, "title": c.title, "dataset_id": c.dataset_id} for c in db.query(Conversation).filter_by(user_id=u.id).order_by(Conversation.id.desc())]

@app.post("/api/conversations")
def new_conv(b: ConvIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not db.query(Dataset).filter_by(id=b.dataset_id, user_id=u.id).first(): raise HTTPException(404, "Dataset not found.")
    c = Conversation(user_id=u.id, dataset_id=b.dataset_id); db.add(c); db.commit()
    return {"id": c.id, "title": c.title, "dataset_id": c.dataset_id}

@app.get("/api/conversations/{cid}")
def get_conv(cid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    _conv(db, u, cid)
    return [msg_out(m) for m in db.query(Message).filter_by(conversation_id=cid).order_by(Message.id)]

@app.delete("/api/conversations/{cid}")
def del_conv(cid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _conv(db, u, cid); db.query(Message).filter_by(conversation_id=cid).delete(); db.delete(c); db.commit(); return {"ok": True}

@app.post("/api/conversations/{cid}/ask")
def ask(cid: int, b: AskIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _conv(db, u, cid); ds = db.get(Dataset, c.dataset_id)
    if not ds: raise HTTPException(404, "Dataset was deleted.")
    try: df = load_dataframe(ds.path)
    except AnalysisError as e: raise HTTPException(400, e.message)

    # last assistant message -> previous plan (for follow-up filters etc.)
    last = db.query(Message).filter_by(conversation_id=cid, role="assistant").order_by(Message.id.desc()).first()
    prev = (last.result or {}).get("plan") if last else None

    # last assistant message that has a real computed result -> used for "explain this"
    msgs = db.query(Message).filter_by(conversation_id=cid, role="assistant").order_by(Message.id.desc()).limit(10).all()
    prev_output = next((m.result for m in msgs if isinstance(m.result, dict) and m.result.get("result")), None)

    out = run_question(df, ds.profile, b.question, b.language, prev, prev_output)
    if c.title == "New chat": c.title = b.question[:48]
    db.add(Message(conversation_id=cid, role="user", content=b.question))
    a = Message(conversation_id=cid, role="assistant", content=out["explanation"], result=out); db.add(a); db.commit()
    return msg_out(a)

app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")