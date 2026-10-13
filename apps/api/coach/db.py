import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint, Uuid, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .config import settings


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class User(Base):  # Local development only; never created in production.
    __tablename__ = "local_users"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    display_name: Mapped[str] = mapped_column(String)
    goal_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    goal_time_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    runs_per_week: Mapped[int] = mapped_column(Integer, default=3)
    athlete_settings: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))


class Crew(Base):
    __tablename__ = "crews"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String)
    owner_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"))


class Member(Base):
    __tablename__ = "memberships"
    crew_id: Mapped[str] = mapped_column(ForeignKey("crews.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String, default="member")
    status: Mapped[str] = mapped_column(String, default="pending")
    share_summary: Mapped[bool] = mapped_column(Boolean, default=False)


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    crew_id: Mapped[str] = mapped_column(ForeignKey("crews.id", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String, unique=True)
    expires_at: Mapped[float] = mapped_column(Float)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("user_id", "sha256"),)
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    file_key: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, default=now)
    status: Mapped[str] = mapped_column(String, default="queued")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    workout_notes: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[float | None] = mapped_column(Float, nullable=True)


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("user_id", "week_start"),)
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    week_start: Mapped[str] = mapped_column(String)
    prescription: Mapped[dict] = mapped_column(JSON)


class Completion(Base):
    __tablename__ = "completions"
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), primary_key=True)
    day_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[str] = mapped_column(String, default=now)


_engine = None


def engine():
    global _engine
    if _engine is None:
        cfg = settings()
        if cfg.mode != "production":
            cfg.data_dir.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(cfg.database_url, pool_pre_ping=True,
                                connect_args={"check_same_thread": False} if cfg.database_url.startswith("sqlite") else {})
        if cfg.database_url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def sqlite_config(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA busy_timeout=10000")
    return _engine


def initialize():
    if settings().mode != "production":
        Base.metadata.create_all(engine())
        # Preserve existing local accounts/GPX when upgrading a development DB.
        with engine().begin() as connection:
            for table, column in [('profiles', 'athlete_settings'), ('runs', 'workout_notes')]:
                if column not in {c['name'] for c in inspect(connection).get_columns(table)}:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} JSON NOT NULL DEFAULT '{{}}'"))


def session(user_id=None):
    db = Session(engine(), expire_on_commit=False)
    if user_id and settings().mode == "production":
        db.execute(text("SET LOCAL ROLE authenticated"))
        db.execute(text("SELECT set_config('request.jwt.claims', :claims, true)"),
                   {"claims": __import__("json").dumps({"sub": user_id, "role": "authenticated"})})
    return db


def dump(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
