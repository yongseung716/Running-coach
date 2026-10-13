import hashlib
import json
import secrets
import tempfile
import time
import zipfile
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from copy import deepcopy
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import auth, storage
from .analysis import VERSION, GPXError, parse_gpx
from .activity import prepare_upload, private_route
from .feedback import feedback
from .training import catalog, build_day, plan_warnings
from .coaching import prescribe
from .config import settings
from .db import Completion, Crew, Invite, Member, Plan, Profile, Run, User, dump, initialize, session, uid


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="Running Coach API", version="1.1.0", lifespan=lifespan)
_limits = defaultdict(deque)


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > settings().max_upload_bytes + 65536:
                raise HTTPException(413, "요청 본문이 너무 큽니다.")
            return message
        await self.app(scope, bounded_receive, send)


app.add_middleware(BodyLimitMiddleware)


@app.middleware("http")
async def security(request: Request, call_next):
    unsafe = request.method not in {"GET", "HEAD", "OPTIONS"}
    if unsafe:
        origin = request.headers.get("origin")
        bearer = request.headers.get("authorization", "").startswith("Bearer ")
        if not bearer and origin not in settings().origins:
            return JSONResponse({"detail": "허용된 출처에서 요청하세요."}, status_code=403)
        if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > settings().max_upload_bytes + 65536:
            return JSONResponse({"detail": "요청 본문이 너무 큽니다."}, status_code=413)
        # Per-process protection. Deployment also requires an edge rate limit.
        key = ((request.client.host if request.client else "unknown"), "auth" if request.url.path.startswith("/auth/") else "write")
        stamps = _limits[key]
        cutoff = time.monotonic() - 60
        while stamps and stamps[0] < cutoff:
            stamps.popleft()
        if len(stamps) >= (20 if key[1] == "auth" else 120):
            return JSONResponse({"detail": "잠시 후 다시 시도하세요."}, status_code=429)
        stamps.append(time.monotonic())
        if len(_limits) > 5000:
            for stale in list(_limits):
                if not _limits[stale] or _limits[stale][-1] < cutoff:
                    _limits.pop(stale, None)
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse({"detail": "이미 존재하거나 다른 요청과 충돌했습니다. 새로고침 후 확인하세요."}, status_code=409)


def db_for_user(user_id=Depends(auth.current_user)):
    with session(user_id) as db:
        yield db
        db.commit()


def valid_id(value: str):
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise HTTPException(404, "기록을 찾을 수 없습니다.") from exc


def mine(db, model, object_id, user_id):
    obj = db.get(model, valid_id(object_id))
    if obj is None or obj.user_id != user_id:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    return obj


def membership(db, crew_id, user_id, roles=None):
    member = db.get(Member, (valid_id(crew_id), user_id))
    if member is None or member.status != "active" or (roles and member.role not in roles):
        raise HTTPException(403, "크루 권한이 없습니다.")
    return member


def rpc(db, name, **kwargs):
    # Function name/argument names are hard-coded by callers; values always bound.
    args = ", ".join(f"CAST(:{key} AS uuid)" if key in {"p_crew", "p_user", "p_run"} else f":{key}" for key in kwargs)
    return db.scalar(text(f"SELECT public.{name}({args})"), kwargs)


def public_run(run):
    return {**{k: v for k, v in dump(run).items() if k not in {"file_key", "sha256", "lease_until"}},
            "file_format": run.file_key.rsplit('.', 1)[-1]}


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(Input):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(default="Runner", min_length=1, max_length=40)


class ProfileInput(Input):
    display_name: str = Field(min_length=1, max_length=40)
    goal_distance_km: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    goal_time_min: float | None = Field(default=None, gt=0, le=1440, allow_inf_nan=False)
    runs_per_week: int = Field(default=3, ge=2, le=5)


class CrewInput(Input):
    name: str = Field(min_length=1, max_length=60)


class JoinInput(Input):
    code: str = Field(min_length=10, max_length=128)


class MemberInput(Input):
    status: str | None = Field(default=None, pattern="^(active|rejected)$")
    role: str | None = Field(default=None, pattern="^(admin|member)$")


class ConsentInput(Input):
    share_summary: bool


class TransferInput(Input):
    user_id: UUID


class CompleteInput(Input):
    run_id: UUID | None = None


class DeleteAccount(Input):
    confirm: str = Field(pattern="^DELETE$")


class AthleteSettings(Input):
    hr_max: int | None = Field(default=None, ge=100, le=240)
    lthr: int | None = Field(default=None, ge=90, le=220)
    benchmark_5k_min: float | None = Field(default=None, gt=10, le=150, allow_inf_nan=False)
    benchmark_10k_min: float | None = Field(default=None, gt=20, le=300, allow_inf_nan=False)
    benchmark_date: date | None = None
    benchmark_5k_date: date | None = None
    benchmark_10k_date: date | None = None

    @model_validator(mode='after')
    def consistent(self):
        if self.hr_max and self.lthr and self.lthr >= self.hr_max:
            raise ValueError('역치심박은 최대심박보다 낮아야 합니다.')
        today = datetime.now(timezone.utc).date()
        for distance in (5, 10):
            stamp = getattr(self, f'benchmark_{distance}k_date') or self.benchmark_date
            if getattr(self, f'benchmark_{distance}k_min') and stamp is None:
                raise ValueError('실제 기록의 날짜를 함께 입력하세요.')
            if stamp and stamp > today:
                raise ValueError('미래의 경기 기록을 근거로 사용할 수 없습니다.')
        return self


class GarminExtras(Input):
    primary_benefit: str | None = Field(default=None, max_length=80)
    self_evaluation: str | None = Field(default=None, max_length=80)
    calories_active_kcal: float | None = Field(default=None, ge=0, le=50000, allow_inf_nan=False)
    calories_resting_kcal: float | None = Field(default=None, ge=0, le=50000, allow_inf_nan=False)
    calories_intake_kcal: float | None = Field(default=None, ge=0, le=50000, allow_inf_nan=False)
    sweat_loss_ml: float | None = Field(default=None, ge=0, le=20000, allow_inf_nan=False)
    fluid_intake_ml: float | None = Field(default=None, ge=0, le=20000, allow_inf_nan=False)
    body_battery_delta: int | None = Field(default=None, ge=-100, le=100)
    grade_adjusted_pace_sec_km: float | None = Field(default=None, ge=75, le=1800, allow_inf_nan=False)
    running_seconds: float | None = Field(default=None, ge=0, le=172800, allow_inf_nan=False)
    walking_seconds: float | None = Field(default=None, ge=0, le=172800, allow_inf_nan=False)
    idle_seconds: float | None = Field(default=None, ge=0, le=172800, allow_inf_nan=False)
    intensity_moderate_min: float | None = Field(default=None, ge=0, le=2880, allow_inf_nan=False)
    intensity_vigorous_min: float | None = Field(default=None, ge=0, le=2880, allow_inf_nan=False)


class WorkoutNotes(Input):
    training_type: Literal['unspecified', 'easy', 'interval', 'tempo', 'steady', 'lsd', 'race'] = 'unspecified'
    rpe: int | None = Field(default=None, ge=1, le=10)
    note: str = Field(default='', max_length=2000)
    garmin: GarminExtras = Field(default_factory=GarminExtras)


class WorkoutSpec(Input):
    type: Literal['rest', 'easy', 'interval', 'tempo', 'steady', 'lsd']
    mode: Literal['pace', 'hr', 'rpe'] | None = None
    distance_km: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    duration_min: float | None = Field(default=None, gt=0, le=600, allow_inf_nan=False)
    repetitions: int = Field(default=4, ge=1, le=20)
    repeat_distance_m: int = Field(default=400, ge=100, le=5000)
    recovery_distance_m: int = Field(default=200, ge=0, le=5000)
    warmup_km: float = Field(default=1, ge=0, le=10, allow_inf_nan=False)
    cooldown_km: float = Field(default=1, ge=0, le=10, allow_inf_nan=False)
    pace_low_sec_km: float | None = Field(default=None, ge=75, le=1800, allow_inf_nan=False)
    pace_high_sec_km: float | None = Field(default=None, ge=75, le=1800, allow_inf_nan=False)
    hr_low: int | None = Field(default=None, ge=30, le=240)
    hr_high: int | None = Field(default=None, ge=30, le=240)

    @model_validator(mode='after')
    def one_volume(self):
        if self.distance_km is not None and self.duration_min is not None:
            raise ValueError('거리와 시간 중 하나를 선택하세요.')
        return self


@app.get("/health")
def health():
    with session() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "mode": settings().mode, "engine_version": VERSION}


@app.post("/auth/signup", status_code=201)
def signup(body: Credentials, response: Response):
    if settings().mode == "production":
        result = auth.gotrue("signup", {"email": str(body.email), "password": body.password,
                                        "data": {"display_name": body.display_name}})
        if result.get("access_token"):
            auth.set_session(response, result["access_token"], result.get("refresh_token"), result.get("expires_in", 3600))
        return {"message": "가입 요청이 접수되었습니다. 이메일 확인이 필요할 수 있습니다.",
                "authenticated": bool(result.get("access_token"))}
    with session() as db:
        user = User(email=str(body.email).lower(), password_hash=auth.password_hash(body.password))
        db.add(user)
        db.flush()
        db.add(Profile(id=user.id, display_name=body.display_name))
        db.commit()
        auth.set_session(response, auth.issue(user.id), expires=86400)
    return {"message": "개발 계정이 생성되었습니다.", "authenticated": True}


@app.post("/auth/login")
def login(body: Credentials, response: Response):
    if settings().mode == "production":
        result = auth.gotrue("token?grant_type=password", {"email": str(body.email), "password": body.password})
        auth.set_session(response, result["access_token"], result["refresh_token"], result.get("expires_in", 3600))
    else:
        with session() as db:
            user = db.scalar(select(User).where(User.email == str(body.email).lower()))
            if not user or not auth.password_matches(body.password, user.password_hash):
                raise HTTPException(401, "이메일 또는 비밀번호가 일치하지 않습니다.")
            auth.set_session(response, auth.issue(user.id), expires=86400)
    return {"message": "로그인되었습니다."}


@app.post("/auth/refresh")
def refresh(request: Request, response: Response):
    if settings().mode != "production":
        raise HTTPException(401, "다시 로그인하세요.")
    token = request.cookies.get("rc_refresh")
    if not token:
        raise HTTPException(401, "다시 로그인하세요.")
    result = auth.gotrue("token?grant_type=refresh_token", {"refresh_token": token})
    auth.set_session(response, result["access_token"], result["refresh_token"], result.get("expires_in", 3600))
    return {"message": "세션이 갱신되었습니다."}


@app.post("/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("rc_access")
    if settings().mode == "production" and token:
        auth.gotrue("logout", token=token)
    response.delete_cookie("rc_access", path="/")
    response.delete_cookie("rc_refresh", path="/")
    return {"message": "로그아웃되었습니다."}


@app.get("/profile")
def profile(user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    obj = db.get(Profile, user_id)
    if not obj:
        raise HTTPException(404, "프로필이 없습니다.")
    return dump(obj)


@app.patch("/profile")
def update_profile(body: ProfileInput, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    if (body.goal_distance_km is None) != (body.goal_time_min is None):
        raise HTTPException(422, "목표 거리와 시간을 함께 입력하세요.")
    obj = db.get(Profile, user_id)
    if obj is None:
        raise HTTPException(404, "프로필이 없습니다.")
    for key, value in body.model_dump().items():
        setattr(obj, key, value)
    return dump(obj)


@app.get("/crews")
def crews(user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    rows = db.execute(select(Crew, Member).join(Member, Member.crew_id == Crew.id).where(Member.user_id == user_id)).all()
    return [{**dump(c), "membership": dump(m)} for c, m in rows]


@app.patch('/profile/athlete-settings')
def update_athlete(body: AthleteSettings, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope='function')):
    obj = db.get(Profile, user_id)
    obj.athlete_settings = body.model_dump(mode='json')
    return dump(obj)


def own_analyses(db, user_id):
    return [r.analysis for r in db.scalars(select(Run).where(Run.user_id == user_id, Run.status == 'completed').order_by(Run.created_at.desc()).limit(2000)) if r.analysis]


@app.get('/training/catalog')
def training_catalog(user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope='function')):
    return catalog(dump(db.get(Profile, user_id)), own_analyses(db, user_id))


@app.post("/crews", status_code=201)
def create_crew(body: CrewInput, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    if settings().mode == "production":
        crew_id = rpc(db, "create_crew", p_name=body.name)
        return dump(db.get(Crew, str(crew_id)))
    crew = Crew(name=body.name, owner_id=user_id)
    db.add(crew)
    db.flush()
    db.add(Member(crew_id=crew.id, user_id=user_id, role="owner", status="active", share_summary=False))
    return dump(crew)


@app.post("/crews/join")
def join(body: JoinInput, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    hashed = hashlib.sha256(body.code.encode()).hexdigest()
    if settings().mode == "production":
        crew_id = rpc(db, "request_join", p_hash=hashed)
        if crew_id is None:
            raise HTTPException(404, "초대 코드가 유효하지 않거나 만료되었습니다.")
        return {"crew_id": str(crew_id), "status": "pending"}
    invite = db.scalar(select(Invite).where(Invite.code_hash == hashed, Invite.expires_at > time.time()))
    if not invite:
        raise HTTPException(404, "초대 코드가 유효하지 않거나 만료되었습니다.")
    existing = db.get(Member, (invite.crew_id, user_id))
    if existing:
        raise HTTPException(409, "이미 요청하거나 가입한 크루입니다.")
    db.add(Member(crew_id=invite.crew_id, user_id=user_id, status="pending", role="member", share_summary=False))
    return {"crew_id": invite.crew_id, "status": "pending"}


@app.get("/crews/{crew_id}")
def crew_detail(crew_id: str, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    member = membership(db, crew_id, user_id)
    rows = db.scalars(select(Member).where(Member.crew_id == crew_id)).all()
    visible = rows if member.role in {"owner", "admin"} else [m for m in rows if m.status == "active"]
    return {**dump(db.get(Crew, valid_id(crew_id))), "members": [dump(m) for m in visible]}


@app.post("/crews/{crew_id}/invites")
def invite(crew_id: str, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    membership(db, crew_id, user_id, {"owner", "admin"})
    code = secrets.token_urlsafe(24)
    expires = time.time() + 7 * 86400
    db.add(Invite(crew_id=crew_id, code_hash=hashlib.sha256(code.encode()).hexdigest(), expires_at=expires))
    return {"code": code, "expires_at": expires}


@app.patch("/crews/{crew_id}/members/{target_id}")
def update_member(crew_id: str, target_id: str, body: MemberInput,
                  user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    caller = membership(db, crew_id, user_id, {"owner", "admin"})
    target = db.get(Member, (valid_id(crew_id), valid_id(target_id)))
    if not target:
        raise HTTPException(404, "회원을 찾을 수 없습니다.")
    if target.role == "owner" or (caller.role == "admin" and (target.role != "member" or body.role is not None)):
        raise HTTPException(403, "소유자 보호 또는 관리자 지정 권한이 없습니다.")
    if body.status is not None and target.status != "pending":
        raise HTTPException(409, "승인/거절은 대기 중인 회원만 가능합니다.")
    if body.role is not None and target.status != "active":
        raise HTTPException(409, "활성 회원만 역할을 변경할 수 있습니다.")
    if settings().mode == "production":
        rpc(db, "manage_member", p_crew=crew_id, p_user=target_id, p_status=body.status, p_role=body.role)
        db.expire(target)
    else:
        if body.status:
            target.status = body.status
        if body.role:
            target.role = body.role
    return dump(target)


@app.patch("/crews/{crew_id}/consent")
def consent(crew_id: str, body: ConsentInput, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    member = membership(db, crew_id, user_id)
    if settings().mode == "production":
        rpc(db, "set_consent", p_crew=crew_id, p_share=body.share_summary)
        db.expire(member)
    else:
        member.share_summary = body.share_summary
    return dump(member)


@app.post("/crews/{crew_id}/transfer")
def transfer(crew_id: str, body: TransferInput, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    owner = membership(db, crew_id, user_id, {"owner"})
    target_id = str(body.user_id)
    target = membership(db, crew_id, target_id)
    if target_id == user_id:
        raise HTTPException(422, "다른 활성 회원을 선택하세요.")
    if settings().mode == "production":
        rpc(db, "transfer_crew", p_crew=crew_id, p_user=target_id)
    else:
        owner.role = "admin"
        target.role = "owner"
        db.get(Crew, crew_id).owner_id = target_id
    return {"message": "소유권을 양도했습니다."}


@app.delete("/crews/{crew_id}/membership")
def leave(crew_id: str, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    member = db.get(Member, (valid_id(crew_id), user_id))
    if not member:
        raise HTTPException(404, "가입 내역이 없습니다.")
    if member.role == "owner":
        raise HTTPException(409, "소유권을 다른 활성 회원에게 양도하세요.")
    db.delete(member)
    return {"message": "탈퇴했습니다."}


@app.get("/crews/{crew_id}/summary")
def crew_summary(crew_id: str, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    membership(db, crew_id, user_id)
    if settings().mode == "production":
        return rpc(db, "crew_summary", p_crew=crew_id)
    people = db.scalars(select(Member).where(Member.crew_id == crew_id, Member.status == "active", Member.share_summary.is_(True))).all()
    if len(people) < 3:
        return {"consenting_members": len(people), "suppressed": True, "distance_km": None, "run_count": None}
    ids = [m.user_id for m in people]
    runs = db.scalars(select(Run).where(Run.user_id.in_(ids), Run.status == "completed")).all()
    analyses = recent_analyses(runs)
    return {"consenting_members": len(people), "suppressed": False,
            "distance_km": round(sum(a["distance_km"] for a in analyses), 2), "run_count": len(analyses)}


def recent_analyses(runs, days=28):
    today = datetime.now(timezone.utc).date()
    values = []
    for run in runs:
        a = run.analysis
        if not a or not a.get("started_at"):
            continue
        try:
            day = datetime.fromisoformat(a["started_at"]).date()
        except ValueError:
            continue
        if 0 <= (today - day).days < days:
            values.append(a)
    return values


@app.post("/runs", status_code=202)
def upload(file: UploadFile, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    data = file.file.read(settings().max_upload_bytes + 1)
    file.file.close()
    if len(data) > settings().max_upload_bytes:
        raise HTTPException(413, "GPX 파일은 10 MiB 이하여야 합니다.")
    try:
        data, extension = prepare_upload(data, file.filename)
    except GPXError as exc:
        raise HTTPException(422, str(exc)) from exc
    sha = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Run).where(Run.user_id == user_id, Run.sha256 == sha))
    if existing:
        return public_run(existing)
    run_id = uid()
    key = f"{user_id}/{run_id}.{extension}"
    try:
        storage.put(key, data)
        run = Run(id=run_id, user_id=user_id, file_key=key, sha256=sha)
        db.add(run)
        db.flush()
        # Commit while compensation still owns the uploaded object.
        db.commit()
    except Exception:
        storage.delete(key)
        raise
    return public_run(run)


@app.get("/runs")
def runs(cursor: str | None = None, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    query = select(Run).where(Run.user_id == user_id)
    if cursor:
        previous = mine(db, Run, cursor, user_id)
        query = query.where((Run.created_at < previous.created_at) | ((Run.created_at == previous.created_at) & (Run.id < previous.id)))
    items = db.scalars(query.order_by(Run.created_at.desc(), Run.id.desc()).limit(101)).all()
    return {"items": [public_run(r) for r in items[:100]], "next_cursor": items[99].id if len(items) > 100 else None}


@app.get("/runs/{run_id}")
def run_detail(run_id: str, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    return public_run(mine(db, Run, run_id, user_id))


@app.get("/runs/{run_id}/file")
def raw_file(run_id: str, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    run = mine(db, Run, run_id, user_id)
    extension = run.file_key.rsplit(".", 1)[-1]
    return Response(storage.get(run.file_key), media_type="application/octet-stream" if extension == "fit" else "application/gpx+xml",
                    headers={"Content-Disposition": f'attachment; filename="{run.id}.{extension}"'})


@app.delete("/runs/{run_id}")
def delete_run(run_id: str, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    run = mine(db, Run, run_id, user_id)
    storage.delete(run.file_key)
    db.delete(run)
    return {"message": "원본과 분석 기록을 삭제했습니다."}


@app.get('/runs/{run_id}/feedback')
def run_feedback(run_id: str, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope='function')):
    run = mine(db, Run, run_id, user_id)
    if run.status != 'completed' or not run.analysis:
        raise HTTPException(409, '분석 완료 후 코칭을 확인하세요.')
    return feedback(run.analysis, run.workout_notes or {}, dump(db.get(Profile, user_id)), own_analyses(db, user_id))


@app.patch('/runs/{run_id}/notes')
def run_notes(run_id: str, body: WorkoutNotes, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope='function')):
    run = mine(db, Run, run_id, user_id)
    run.workout_notes = body.model_dump()
    return public_run(run)


@app.get('/runs/{run_id}/route')
def run_route(run_id: str, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope='function')):
    run = mine(db, Run, run_id, user_id)
    return private_route(storage.get(run.file_key), run.file_key.rsplit('.', 1)[-1])


@app.post('/runs/{run_id}/reanalyze', status_code=202)
def reanalyze(run_id: str, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope='function')):
    run = mine(db, Run, run_id, user_id)
    if run.status not in {'completed', 'failed'}:
        raise HTTPException(409, '이미 처리 중인 기록입니다.')
    if settings().mode == 'production':
        if not rpc(db, 'request_reanalysis', p_run=run.id):
            raise HTTPException(409, '이미 처리 중인 기록입니다.')
        db.refresh(run)
    else:
        run.status, run.attempts, run.analysis, run.error, run.lease_until = 'queued', 0, None, None, None
    return public_run(run)


@app.get("/dashboard")
def dashboard(user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    rows = db.scalars(select(Run).where(Run.user_id == user_id, Run.status == "completed")).all()
    recent = recent_analyses(rows)
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=today.weekday())
    weekly = []
    for offset in range(3, -1, -1):
        monday = start - timedelta(weeks=offset)
        distance = sum(a["distance_km"] for a in recent if monday <= datetime.fromisoformat(a["started_at"]).date() < monday + timedelta(days=7))
        weekly.append({"week_start": monday.isoformat(), "distance_km": round(distance, 2)})
    return {"distance_28d_km": round(sum(a["distance_km"] for a in recent), 2), "runs_28d": len(recent), "weekly": weekly,
            "note": "운동 시작일 기준 최근 28일. 날짜 없는 기록과 미래 기록은 집계에서 제외됩니다."}


def plan_output(db, plan, user_id):
    return {**dump(plan), "completions": [dump(c) for c in db.scalars(select(Completion).where(Completion.plan_id == plan.id, Completion.user_id == user_id))]}


@app.get("/plans")
def plans(user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    rows = db.scalars(select(Plan).where(Plan.user_id == user_id).order_by(Plan.week_start.desc()).limit(12)).all()
    return [plan_output(db, p, user_id) for p in rows]


@app.post("/plans", status_code=201)
def generate_plan(user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    profile = db.get(Profile, user_id)
    rows = db.scalars(select(Run).where(Run.user_id == user_id, Run.status == "completed")).all()
    prescription = prescribe(dump(profile), [r.analysis for r in rows if r.analysis])
    plan = db.scalar(select(Plan).where(Plan.user_id == user_id, Plan.week_start == prescription["week_start"]))
    if not plan:
        plan = Plan(user_id=user_id, week_start=prescription["week_start"], prescription=prescription)
        db.add(plan)
        db.flush()
    return plan_output(db, plan, user_id)


@app.patch('/plans/{plan_id}/days/{day_index}')
def edit_day(plan_id: str, day_index: int, body: WorkoutSpec, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope='function')):
    plan = mine(db, Plan, plan_id, user_id)
    if not 0 <= day_index <= 6:
        raise HTTPException(422, '요일은 0~6이어야 합니다.')
    if db.get(Completion, (plan.id, day_index)):
        raise HTTPException(409, '완료 기록을 취소한 뒤 훈련을 편집하세요.')
    prescription = deepcopy(plan.prescription)
    ref = catalog(dump(db.get(Profile, user_id)), own_analyses(db, user_id))['reference']
    try:
        prescription['days'][day_index] = build_day(prescription['days'][day_index], body.model_dump(), ref)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    prescription['editing_warnings'] = plan_warnings(prescription['days'], prescription.get('basis', {}).get('weekly_target_km'))
    plan.prescription = prescription
    return plan_output(db, plan, user_id)


@app.put("/plans/{plan_id}/days/{day_index}/completion")
def complete(plan_id: str, day_index: int, body: CompleteInput, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    plan = mine(db, Plan, plan_id, user_id)
    if not 0 <= day_index <= 6 or plan.prescription["days"][day_index]["type"] == "rest":
        raise HTTPException(422, "달리기 훈련일만 완료할 수 있습니다.")
    run_id = str(body.run_id) if body.run_id else None
    if run_id and mine(db, Run, run_id, user_id).status != "completed":
        raise HTTPException(422, "분석이 완료된 본인 기록만 연결할 수 있습니다.")
    existing = db.get(Completion, (plan.id, day_index))
    if existing:
        existing.run_id = run_id
    else:
        existing = Completion(plan_id=plan.id, day_index=day_index, user_id=user_id, run_id=run_id)
        db.add(existing)
    db.flush()
    return dump(existing)


@app.delete("/plans/{plan_id}/days/{day_index}/completion")
def uncomplete(plan_id: str, day_index: int, user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    mine(db, Plan, plan_id, user_id)
    item = db.get(Completion, (valid_id(plan_id), day_index))
    if item:
        db.delete(item)
    return {"message": "완료 표시를 취소했습니다."}


@app.get("/account/export")
def export_account(user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    data = {"exported_at": datetime.now(timezone.utc).isoformat(), "profile": dump(db.get(Profile, user_id)),
            "memberships": [dump(m) for m in db.scalars(select(Member).where(Member.user_id == user_id))],
            "plans": [plan_output(db, p, user_id) for p in db.scalars(select(Plan).where(Plan.user_id == user_id))]}
    rows = db.scalars(select(Run).where(Run.user_id == user_id)).all()
    data["runs"] = [public_run(r) for r in rows]
    stream = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
    try:
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("account.json", json.dumps(data, ensure_ascii=False, indent=2))
            for run in rows:
                extension = run.file_key.rsplit(".", 1)[-1]
                archive.writestr(f"{extension}/{run.id}.{extension}", storage.get(run.file_key))
        stream.seek(0)
    except Exception:
        stream.close()
        raise

    def chunks():
        try:
            while chunk := stream.read(65536):
                yield chunk
        finally:
            stream.close()
    return StreamingResponse(chunks(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="running-coach-export.zip"'})


@app.delete("/account")
def delete_account(body: DeleteAccount, request: Request, response: Response,
                   user_id=Depends(auth.current_user), db: Session = Depends(db_for_user, scope="function")):
    claims = auth.current_claims(request)
    # Supabase refresh changes iat. Use the earliest password/OTP AMR timestamp where available.
    auth_times = [entry["timestamp"] for entry in claims.get("amr", []) if entry.get("method") in {"password", "otp"} and "timestamp" in entry]
    if settings().mode == "production" and not auth_times:
        raise HTTPException(403, "비밀번호 또는 OTP로 다시 인증한 뒤 삭제하세요.")
    authenticated_at = min(auth_times) if auth_times else claims.get("auth_time", claims["iat"])
    if time.time() - authenticated_at > 900:
        raise HTTPException(403, "계정 삭제 전 다시 로그인하세요 (15분 이내 인증 필요).")
    if db.scalar(select(Crew).where(Crew.owner_id == user_id)):
        raise HTTPException(409, "소유한 크루의 소유권을 먼저 양도하세요.")
    rows = db.scalars(select(Run).where(Run.user_id == user_id)).all()
    for run in rows:
        storage.delete(run.file_key)
    if settings().mode == "production":
        # Auth deletion cascades profiles/data. Release user transaction before external deletion.
        db.rollback()
        auth.gotrue(f"admin/users/{user_id}", method="DELETE", admin=True)
    else:
        db.execute(delete(Profile).where(Profile.id == user_id))
        db.execute(delete(User).where(User.id == user_id))
    response.delete_cookie("rc_access", path="/")
    response.delete_cookie("rc_refresh", path="/")
    return {"message": "계정과 소유 데이터를 삭제했습니다."}
