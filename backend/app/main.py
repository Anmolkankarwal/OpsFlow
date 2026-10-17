from __future__ import annotations
import base64, hashlib, hmac, json, os, secrets, time
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Generator, Optional
from fastapi import FastAPI, Depends, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
                        create_engine, select, update, func, or_)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session
from sqlalchemy.exc import IntegrityError

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./opsflow.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-this-secret-before-deployment")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase): pass
class Role(str, Enum):
    VIEWER = "Viewer"
    MEMBER = "Member"
    LEAD = "Lead"
    ADMIN = "Admin"
class WorkStatus(str, Enum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    AWAITING_APPROVAL = "Awaiting Approval"
    RESOLVED = "Resolved"
    CLOSED = "Closed"
class Priority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    URGENT = "Urgent"
class WorkType(str, Enum):
    INCIDENT = "Incident"
    CUSTOMER_ISSUE = "Customer Issue"
    PAYMENT = "Payment"
    COMPLIANCE = "Compliance"
    TASK = "Task"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "team_id", name="uq_membership_user_team"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
class WorkItem(Base):
    __tablename__ = "work_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    item_type: Mapped[str] = mapped_column(String(40), default=WorkType.TASK.value)
    priority: Mapped[str] = mapped_column(String(20), default=Priority.MEDIUM.value, index=True)
    status: Mapped[str] = mapped_column(String(30), default=WorkStatus.OPEN.value, index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class ActivityEvent(Base):
    __tablename__ = "activity_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60))
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class IdempotencyPayload(Base):
    __tablename__ = "idempotency_payloads"
    key: Mapped[str] = mapped_column(ForeignKey("idempotency_records.key", ondelete="CASCADE"), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
class OutboxJob(Base):
    __tablename__ = "outbox_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class LoginIn(BaseModel): email: str; password: str
class CreateItem(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=10000)
    item_type: WorkType = WorkType.TASK
    priority: Priority = Priority.MEDIUM
    team_id: int
    assignee_id: Optional[int] = None
    due_date: Optional[datetime] = None
class UpdateItem(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    priority: Optional[Priority] = None
    assignee_id: Optional[int] = None
    due_date: Optional[datetime] = None
    version: int = Field(ge=1)
class TransitionIn(BaseModel): target_status: WorkStatus; version: int = Field(ge=1)
class CommentIn(BaseModel): body: str = Field(min_length=1, max_length=4000)
class UserOut(BaseModel): id: int; name: str; email: str
class ItemOut(BaseModel):
    id: int; title: str; description: str; item_type: str; priority: str; status: str
    team_id: int; assignee_id: Optional[int]; created_by_id: int; due_date: Optional[datetime]
    version: int; created_at: datetime; updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
class ActivityOut(BaseModel): id: int; item_id: int; actor_id: int; action: str; details: str; created_at: datetime; model_config = ConfigDict(from_attributes=True)
class CommentOut(BaseModel): id: int; item_id: int; author_id: int; body: str; created_at: datetime; model_config = ConfigDict(from_attributes=True)

app = FastAPI(title="OpsFlow API", version="1.0.0", description="Team operations and incident-resolution platform")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try: yield db
    finally: db.close()
def _b64(data: bytes) -> str: return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210000)
    return f"{_b64(salt)}${_b64(derived)}"
def verify_password(password: str, stored: str) -> bool:
    try:
        salt_s, digest = stored.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_s + "=" * (-len(salt_s) % 4))
        return hmac.compare_digest(_b64(hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210000)), digest)
    except Exception: return False
def make_token(user_id: int) -> str:
    header = _b64(json.dumps({"alg":"HS256","typ":"JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub":str(user_id),"exp":int(time.time())+60*60*12}, separators=(",", ":")).encode())
    body = f"{header}.{payload}"
    signature = _b64(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"
def decode_token(token: str) -> int:
    try:
        head, payload, signature = token.split(".")
        body = f"{head}.{payload}"
        expected = _b64(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected): raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if int(data["exp"]) < int(time.time()): raise ValueError()
        return int(data["sub"])
    except Exception: raise HTTPException(401, "Invalid or expired bearer token")
def current_user(authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "): raise HTTPException(401, "Bearer token required")
    user = db.get(User, decode_token(authorization.split(" ", 1)[1]))
    if not user or not user.active: raise HTTPException(401, "User is inactive or missing")
    return user
def membership(db: Session, user_id: int, team_id: int) -> Membership:
    m = db.scalar(select(Membership).where(Membership.user_id == user_id, Membership.team_id == team_id))
    if not m: raise HTTPException(403, "You do not belong to this team")
    return m
def require_item(db: Session, user: User, item_id: int) -> tuple[WorkItem, Membership]:
    item = db.get(WorkItem, item_id)
    if not item: raise HTTPException(404, "Work item not found")
    return item, membership(db, user.id, item.team_id)
def record_event(db: Session, item: WorkItem, actor: User, action: str, details: str):
    db.add(ActivityEvent(item_id=item.id, actor_id=actor.id, action=action, details=details))
def can_edit(role: str):
    if role == Role.VIEWER.value: raise HTTPException(403, "Viewers cannot modify work items")
def item_json(item: WorkItem) -> dict:
    return {"id":item.id,"title":item.title,"description":item.description,"item_type":item.item_type,"priority":item.priority,"status":item.status,"team_id":item.team_id,"assignee_id":item.assignee_id,"created_by_id":item.created_by_id,"due_date":item.due_date.isoformat() if item.due_date else None,"version":item.version,"created_at":item.created_at.isoformat(),"updated_at":item.updated_at.isoformat()}

@app.on_event("startup")
def startup(): Base.metadata.create_all(bind=engine)
@app.get("/health")
def health(): return {"status":"ok","service":"opsflow-api"}
@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    if not user or not user.active or not verify_password(data.password, user.password_hash): raise HTTPException(401, "Invalid email or password")
    return {"access_token":make_token(user.id),"token_type":"bearer","user":{"id":user.id,"name":user.name,"email":user.email}}
@app.get("/api/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    return {"id":user.id,"name":user.name,"email":user.email,"teams":[{"team_id":m.team_id,"team_name":db.get(Team,m.team_id).name,"role":m.role} for m in memberships]}
@app.get("/api/teams")
def list_teams(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Team, Membership.role).join(Membership, Membership.team_id == Team.id).where(Membership.user_id == user.id)).all()
    return [{"id":t.id,"name":t.name,"role":role} for t,role in rows]
@app.post("/api/items", response_model=ItemOut, status_code=201)
def create_item(data: CreateItem, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = membership(db, user.id, data.team_id); can_edit(m.role)
    if data.assignee_id is not None and not db.scalar(select(Membership.id).where(Membership.user_id == data.assignee_id, Membership.team_id == data.team_id)):
        raise HTTPException(400, "Assignee must belong to the selected team")
    if idempotency_key:
        if len(idempotency_key) > 200: raise HTTPException(400, "Idempotency-Key must be at most 200 characters")
        request_hash = hashlib.sha256(json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        existing = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key))
        if existing:
            if existing.user_id != user.id: raise HTTPException(409, "Idempotency key belongs to another user")
            payload = db.get(IdempotencyPayload, idempotency_key)
            if not payload or not hmac.compare_digest(payload.request_hash, request_hash):
                raise HTTPException(409, "Idempotency-Key was already used with a different request")
            return db.get(WorkItem, existing.item_id)
    item = WorkItem(title=data.title, description=data.description, item_type=data.item_type.value, priority=data.priority.value, team_id=data.team_id, assignee_id=data.assignee_id, created_by_id=user.id, due_date=data.due_date)
    db.add(item); db.flush()
    record_event(db, item, user, "created", f"Created work item: {item.title}")
    db.add(OutboxJob(event_key=f"item-created-{item.id}", payload=json.dumps({"event":"item.created","item_id":item.id,"assignee_id":item.assignee_id})))
    try:
        if idempotency_key:
            # IdempotencyPayload has a foreign key to IdempotencyRecord.key. SQLAlchemy
            # does not infer insert ordering between these mapped classes without an
            # ORM relationship, so persist the parent explicitly before adding its hash.
            db.add(IdempotencyRecord(key=idempotency_key, user_id=user.id, item_id=item.id))
            db.flush()
            db.add(IdempotencyPayload(key=idempotency_key, request_hash=request_hash))
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key))
            if existing and existing.user_id == user.id:
                payload = db.get(IdempotencyPayload, idempotency_key)
                if payload and hmac.compare_digest(payload.request_hash, request_hash): return db.get(WorkItem, existing.item_id)
                if payload: raise HTTPException(409, "Idempotency-Key was already used with a different request")
        raise HTTPException(409, "Conflicting request; retry with a new idempotency key")
    db.refresh(item); return item
@app.get("/api/items")
def list_items(status_filter: Optional[WorkStatus] = Query(default=None, alias="status"), priority: Optional[Priority] = None, assignee_id: Optional[int] = None, unassigned: bool = False, team_id: Optional[int] = None, q: Optional[str] = None, mine: bool = False, awaiting_my_approval: bool = False, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
    team_ids = list(db.scalars(select(Membership.team_id).where(Membership.user_id == user.id)).all())
    if not team_ids: return {"items":[],"total":0,"page":page,"page_size":page_size,"pages":0}
    stmt = select(WorkItem).where(WorkItem.team_id.in_(team_ids))
    if team_id is not None:
        if team_id not in team_ids: raise HTTPException(403, "You do not belong to this team")
        stmt = stmt.where(WorkItem.team_id == team_id)
    if status_filter: stmt = stmt.where(WorkItem.status == status_filter.value)
    if priority: stmt = stmt.where(WorkItem.priority == priority.value)
    if assignee_id is not None: stmt = stmt.where(WorkItem.assignee_id == assignee_id)
    if unassigned: stmt = stmt.where(WorkItem.assignee_id.is_(None))
    if mine: stmt = stmt.where(WorkItem.assignee_id == user.id)
    if awaiting_my_approval:
        approver_team_ids = db.scalars(select(Membership.team_id).where(Membership.user_id == user.id, Membership.role.in_([Role.LEAD.value, Role.ADMIN.value]))).all()
        stmt = stmt.where(WorkItem.status == WorkStatus.AWAITING_APPROVAL.value, WorkItem.team_id.in_(approver_team_ids))
    if q: stmt = stmt.where(or_(WorkItem.title.ilike(f"%{q}%"), WorkItem.description.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.order_by(WorkItem.updated_at.desc(), WorkItem.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"items":[item_json(i) for i in items],"total":total,"page":page,"page_size":page_size,"pages":(total+page_size-1)//page_size}
@app.get("/api/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    team_ids = list(db.scalars(select(Membership.team_id).where(Membership.user_id == user.id)).all())
    approver_team_ids = list(db.scalars(select(Membership.team_id).where(Membership.user_id == user.id, Membership.role.in_([Role.LEAD.value, Role.ADMIN.value]))).all())
    base = select(WorkItem).where(WorkItem.team_id.in_(team_ids))
    assigned = db.scalars(base.where(WorkItem.assignee_id == user.id).order_by(WorkItem.updated_at.desc()).limit(8)).all()
    urgent = db.scalars(base.where(WorkItem.assignee_id.is_(None), WorkItem.priority == Priority.URGENT.value).order_by(WorkItem.updated_at.desc()).limit(8)).all()
    approval = db.scalars(select(WorkItem).where(WorkItem.team_id.in_(approver_team_ids), WorkItem.status == WorkStatus.AWAITING_APPROVAL.value).order_by(WorkItem.updated_at.desc()).limit(8)).all()
    return {"assigned_to_me":[item_json(i) for i in assigned],"unassigned_urgent":[item_json(i) for i in urgent],"awaiting_my_approval":[item_json(i) for i in approval]}
@app.get("/api/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item, _ = require_item(db,user,item_id); return item
@app.patch("/api/items/{item_id}", response_model=ItemOut)
def update_item(item_id: int, data: UpdateItem, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item, m = require_item(db,user,item_id); can_edit(m.role)
    if item.version != data.version: raise HTTPException(409, detail={"message":"This item changed since you loaded it. Reload and try again.","current_item":item_json(item)})
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    if "assignee_id" in changes and changes["assignee_id"] is not None and not db.scalar(select(Membership.id).where(Membership.user_id == changes["assignee_id"], Membership.team_id == item.team_id)):
        raise HTTPException(400, "Assignee must belong to the item's team")
    old_priority = item.priority; old_assignee = item.assignee_id; old_version = item.version
    # Atomic version bump prevents two concurrent edits from both passing the stale-version check.
    guard = db.execute(update(WorkItem).where(WorkItem.id == item_id, WorkItem.version == data.version).values(version=WorkItem.version + 1), execution_options={"synchronize_session": False})
    if guard.rowcount != 1:
        db.rollback(); latest = db.get(WorkItem, item_id)
        raise HTTPException(409, detail={"message":"This item changed since you loaded it. Reload and try again.","current_item":item_json(latest) if latest else None})
    item.version = old_version + 1
    for key,value in changes.items(): setattr(item,key,value.value if isinstance(value,Enum) else value)
    item.updated_at = datetime.now(timezone.utc)
    if old_priority != item.priority: record_event(db,item,user,"priority_changed",f"{old_priority} → {item.priority}")
    if old_assignee != item.assignee_id: record_event(db,item,user,"assignee_changed",f"{old_assignee} → {item.assignee_id}")
    record_event(db,item,user,"updated","Updated work item fields")
    db.commit(); db.refresh(item); return item
@app.post("/api/items/{item_id}/claim", response_model=ItemOut)
def claim_item(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item, m = require_item(db,user,item_id); can_edit(m.role)
    if item.assignee_id == user.id: return item
    now = datetime.now(timezone.utc)
    old_version = item.version
    result = db.execute(update(WorkItem).where(WorkItem.id == item_id, WorkItem.assignee_id.is_(None), WorkItem.version == old_version).values(assignee_id=user.id, version=WorkItem.version+1, updated_at=now), execution_options={"synchronize_session": False})
    if result.rowcount != 1: db.rollback(); raise HTTPException(409, "This item has already been claimed or changed by another user")
    item.assignee_id=user.id; item.version=old_version+1; item.updated_at=now
    record_event(db,item,user,"claimed",f"Claimed by {user.name}"); db.commit(); db.refresh(item); return item
ALLOWED = {WorkStatus.OPEN.value:{WorkStatus.IN_PROGRESS.value}, WorkStatus.IN_PROGRESS.value:{WorkStatus.AWAITING_APPROVAL.value,WorkStatus.OPEN.value}, WorkStatus.AWAITING_APPROVAL.value:{WorkStatus.RESOLVED.value,WorkStatus.IN_PROGRESS.value}, WorkStatus.RESOLVED.value:{WorkStatus.CLOSED.value,WorkStatus.IN_PROGRESS.value}, WorkStatus.CLOSED.value:set()}
@app.post("/api/items/{item_id}/transition", response_model=ItemOut)
def transition_item(item_id: int, data: TransitionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item,m = require_item(db,user,item_id); can_edit(m.role)
    if item.version != data.version: raise HTTPException(409, detail={"message":"This item changed since you loaded it. Reload and try again.","current_item":item_json(item)})
    target = data.target_status.value
    if target not in ALLOWED.get(item.status,set()): raise HTTPException(400, f"Invalid workflow transition: {item.status} → {target}")
    if item.status == WorkStatus.AWAITING_APPROVAL.value and target == WorkStatus.RESOLVED.value and m.role not in (Role.LEAD.value,Role.ADMIN.value): raise HTTPException(403,"Only a Lead or Admin can approve this item")
    old=item.status; old_version=item.version; now=datetime.now(timezone.utc)
    guard=db.execute(update(WorkItem).where(WorkItem.id==item_id,WorkItem.version==data.version).values(version=WorkItem.version+1), execution_options={"synchronize_session":False})
    if guard.rowcount != 1:
        db.rollback(); latest=db.get(WorkItem,item_id)
        raise HTTPException(409,detail={"message":"This item changed since you loaded it. Reload and try again.","current_item":item_json(latest) if latest else None})
    item.status=target; item.version=old_version+1; item.updated_at=now
    record_event(db,item,user,"status_changed",f"{old} → {target}")
    db.add(OutboxJob(event_key=f"status-{item.id}-{item.version}",payload=json.dumps({"event":"item.status_changed","item_id":item.id,"status":target})))
    db.commit(); db.refresh(item); return item
@app.get("/api/items/{item_id}/activity", response_model=list[ActivityOut])
def get_activity(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_item(db,user,item_id)
    return db.scalars(select(ActivityEvent).where(ActivityEvent.item_id==item_id).order_by(ActivityEvent.created_at.desc(),ActivityEvent.id.desc()).limit(200)).all()
@app.get("/api/items/{item_id}/comments", response_model=list[CommentOut])
def get_comments(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_item(db,user,item_id)
    return db.scalars(select(Comment).where(Comment.item_id==item_id).order_by(Comment.created_at.asc())).all()
@app.post("/api/items/{item_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(item_id: int, data: CommentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item,m=require_item(db,user,item_id); can_edit(m.role)
    comment=Comment(item_id=item.id,author_id=user.id,body=data.body); db.add(comment); db.flush()
    record_event(db,item,user,"comment_added",data.body[:160]); db.commit(); db.refresh(comment); return comment
@app.get("/api/admin/outbox")
def outbox_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    memberships=db.scalars(select(Membership).where(Membership.user_id==user.id)).all()
    if not any(m.role==Role.ADMIN.value for m in memberships): raise HTTPException(403,"Admin role required")
    rows=db.scalars(select(OutboxJob).order_by(OutboxJob.id.desc()).limit(100)).all()
    return [{"id":r.id,"event_key":r.event_key,"payload":r.payload,"status":r.status,"attempts":r.attempts,"created_at":r.created_at.isoformat()} for r in rows]

@app.post("/api/dev/seed")
def seed_demo(db: Session = Depends(get_db)):
    """Local demo helper. Disable by setting DISABLE_DEV_SEED=1 in production."""
    if os.getenv("DISABLE_DEV_SEED", "0") == "1": raise HTTPException(404,"Not found")
    if db.scalar(select(User.id).limit(1)): return {"message":"Seed data already exists"}
    users_data=[("Aarav Admin","admin@opsflow.local","Admin123!"),("Meera Lead","lead@opsflow.local","Lead123!"),("Rohan Member","member@opsflow.local","Member123!"),("Sara Viewer","viewer@opsflow.local","Viewer123!"),("Kabir Other Team","other@opsflow.local","Other123!")]
    users=[]
    for name,email,pw in users_data:
        u=User(name=name,email=email,password_hash=hash_password(pw));db.add(u);users.append(u)
    teams=[Team(name="Operations"),Team(name="Customer Support"),Team(name="Finance")];db.add_all(teams);db.flush()
    for u in users:
        if u.email=="admin@opsflow.local": pairs=[(teams[0],Role.ADMIN.value),(teams[1],Role.ADMIN.value),(teams[2],Role.ADMIN.value)]
        elif u.email=="lead@opsflow.local": pairs=[(teams[0],Role.LEAD.value)]
        elif u.email=="member@opsflow.local": pairs=[(teams[0],Role.MEMBER.value)]
        elif u.email=="viewer@opsflow.local": pairs=[(teams[0],Role.VIEWER.value)]
        else: pairs=[(teams[1],Role.MEMBER.value)]
        for team,role in pairs: db.add(Membership(user_id=u.id,team_id=team.id,role=role))
    db.flush()
    sample=[("Investigate payment retry failures","Review recurring retry errors in payment processing.",WorkType.INCIDENT.value,Priority.URGENT.value,WorkStatus.OPEN.value,teams[0].id,None,users[0].id),("Review customer escalation","Follow up on a delayed customer resolution.",WorkType.CUSTOMER_ISSUE.value,Priority.HIGH.value,WorkStatus.IN_PROGRESS.value,teams[0].id,users[2].id,users[0].id),("Approve compliance checklist","Check quarterly compliance evidence.",WorkType.COMPLIANCE.value,Priority.MEDIUM.value,WorkStatus.AWAITING_APPROVAL.value,teams[0].id,users[2].id,users[1].id),("Reconcile daily settlement","Verify the latest settlement totals.",WorkType.PAYMENT.value,Priority.LOW.value,WorkStatus.OPEN.value,teams[2].id,None,users[0].id)]
    for title,desc,typ,prio,st,tid,aid,cid in sample:
        item=WorkItem(title=title,description=desc,item_type=typ,priority=prio,status=st,team_id=tid,assignee_id=aid,created_by_id=cid);db.add(item);db.flush();db.add(ActivityEvent(item_id=item.id,actor_id=cid,action="created",details=f"Seeded demo item: {title}"))
    db.commit();return {"message":"Demo data created","users":[{"email":e,"password":p} for _,e,p in users_data],"teams":[t.name for t in teams]}
