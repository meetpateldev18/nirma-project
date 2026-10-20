"""
Pytest Test Configuration & Global Fixtures Module.

This module provisions isolated testing infrastructure for the Nirma University
AI Call Agent test suite:
1. In-memory SQLite async and sync database engines with custom SQLite extensions.
2. Isolated database transactions rolled back or recreated per test.
3. Pre-seeded staff users (admin, operator, inactive) with pre-generated JWT tokens.
4. In-memory Async Mock Redis client for deterministic distributed locking and caching.
5. Mock AI Pipeline and Plivo telephony adapters to prevent external network I/O.
6. Async HTTP test client configured for the FastAPI application instance.

Dependencies:
    - pytest
    - pytest-asyncio
    - httpx
    - sqlalchemy[asyncio]
    - aiosqlite
"""

import asyncio
import datetime
import json
import os

# Ensure test environment parameters before any backend imports
os.environ["APP_ENV"] = "testing"
os.environ["DEBUG"] = "true"
os.environ["AUDIO_CACHE_DIR"] = "/tmp/audio_cache"
os.environ["PLIVO_AUTH_ID"] = "mock_plivo_auth"
os.environ["PLIVO_AUTH_TOKEN"] = "mock_plivo_token"
os.environ["TWILIO_ACCOUNT_SID"] = "mock_twilio_account_sid"
os.environ["TWILIO_AUTH_TOKEN"] = "mock_twilio_auth_token"

from typing import Any, AsyncGenerator, Dict, Generator, List, Optional
import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.auth import create_jwt_token, get_password_hash
from backend.config import Settings, settings
from backend.database.models import Base, CallScript, StaffUser, Student, utc_now
from backend.database.session import get_async_session, get_sync_session
from backend.main import app

# Precompute standard bcrypt test hash once at module load to accelerate test execution
_GLOBAL_PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
PRECOMPUTED_TEST_PASSWORD_HASH = _GLOBAL_PWD_CONTEXT.hash("NirmaPassword123!")


# ------------------------------------------------------------------------------
# 1. In-Memory Mock Redis Manager
# ------------------------------------------------------------------------------
class MockRedisPipeline:
    """Mock asynchronous Redis pipeline simulating batched atomic transactions."""

    def __init__(self, redis_store: "MockRedisClient") -> None:
        self.store = redis_store
        self.commands: List[Any] = []

    def hset(self, key: str, mapping: Dict[str, Any]) -> "MockRedisPipeline":
        self.commands.append(("hset", key, mapping))
        return self

    def expire(self, key: str, ttl: int) -> "MockRedisPipeline":
        self.commands.append(("expire", key, ttl))
        return self

    async def execute(self) -> List[Any]:
        results = []
        for cmd in self.commands:
            if cmd[0] == "hset":
                _, key, mapping = cmd
                if key not in self.store._hashes:
                    self.store._hashes[key] = {}
                self.store._hashes[key].update({k: str(v) for k, v in mapping.items()})
                results.append(len(mapping))
            elif cmd[0] == "expire":
                _, key, ttl = cmd
                self.store._ttls[key] = ttl
                results.append(True)
        self.commands.clear()
        return results

    async def __aenter__(self) -> "MockRedisPipeline":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class MockRedisClient:
    """In-memory async Redis client mock for test isolation."""

    def __init__(self) -> None:
        self._keys: Dict[str, str] = {}
        self._hashes: Dict[str, Dict[str, str]] = {}
        self._ttls: Dict[str, int] = {}

    def pipeline(self, transaction: bool = True) -> MockRedisPipeline:
        return MockRedisPipeline(self)

    async def get(self, key: str) -> Optional[str]:
        return self._keys.get(key)

    async def set(
        self,
        key: str,
        value: str,
        nx: bool = False,
        ex: Optional[int] = None,
    ) -> bool:
        if nx and key in self._keys:
            return False
        self._keys[key] = str(value)
        if ex:
            self._ttls[key] = ex
        return True

    async def delete(self, key: str) -> int:
        deleted = 0
        if key in self._keys:
            del self._keys[key]
            deleted = 1
        if key in self._hashes:
            del self._hashes[key]
            deleted = 1
        self._ttls.pop(key, None)
        return deleted

    async def hset(self, key: str, mapping: Dict[str, Any]) -> int:
        if key not in self._hashes:
            self._hashes[key] = {}
        self._hashes[key].update({k: str(v) for k, v in mapping.items()})
        return len(mapping)

    async def hgetall(self, key: str) -> Dict[str, str]:
        return dict(self._hashes.get(key, {}))

    async def expire(self, key: str, ttl: int) -> bool:
        self._ttls[key] = ttl
        return True

    async def ttl(self, key: str) -> int:
        return self._ttls.get(key, -1)

    async def exists(self, key: str) -> int:
        return 1 if (key in self._keys or key in self._hashes) else 0

    async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        # Atomic lock release simulation
        if self._keys.get(key) == token:
            del self._keys[key]
            self._ttls.pop(key, None)
            return 1
        return 0

    async def aclose(self) -> None:
        self._keys.clear()
        self._hashes.clear()
        self._ttls.clear()


class MockRedisManager:
    """Mock Redis manager providing distributed lock and cache-aside methods."""

    def __init__(self) -> None:
        self.client = MockRedisClient()

    def get_client(self) -> MockRedisClient:
        return self.client

    async def acquire_lock(
        self,
        lock_key: str,
        ttl_seconds: int = 15,
        token: Optional[str] = None,
    ) -> tuple[bool, str]:
        import uuid

        lock_token = token or str(uuid.uuid4())
        prefixed_key = f"lock:{lock_key}" if not lock_key.startswith("lock:") else lock_key
        acquired = await self.client.set(prefixed_key, lock_token, nx=True, ex=ttl_seconds)
        return (acquired, lock_token)

    async def release_lock(self, lock_key: str, token: str) -> bool:
        prefixed_key = f"lock:{lock_key}" if not lock_key.startswith("lock:") else lock_key
        res = await self.client.eval("", 1, prefixed_key, token)
        return res == 1

    async def cache_get_json(self, key: str) -> Optional[Any]:
        val = await self.client.get(key)
        if val:
            try:
                return json.loads(val)
            except Exception:
                return None
        return None

    async def cache_set_json(self, key: str, value: Any, ttl_seconds: int = 3600) -> bool:
        serialized = json.dumps(value)
        return await self.client.set(key, serialized, ex=ttl_seconds)

    async def close(self) -> None:
        await self.client.aclose()


# ------------------------------------------------------------------------------
# 2. Database Fixtures (Unified SQLite File Database for Sync & Async)
# ------------------------------------------------------------------------------
@pytest.fixture
def test_db_path():
    """Provides a unique temporary SQLite database file path for complete test isolation."""
    import uuid
    path = f"/tmp/test_nirma_db_{uuid.uuid4().hex}.db"
    yield path
    if os.path.exists(path):
        try:
            os.unlink(path)
        except Exception:
            pass


@pytest.fixture
def sync_test_engine(test_db_path: str):
    """Provides a synchronous SQLite engine with custom to_char SQL function."""
    engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def do_connect(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA synchronous = OFF")
        cursor.execute("PRAGMA journal_mode = MEMORY")
        cursor.close()
        dbapi_connection.create_function(
            "to_char",
            2,
            lambda dt, fmt: str(dt)[:10] if dt else "",
        )

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
async def async_test_engine(test_db_path: str, sync_test_engine):
    """Provides an asynchronous SQLite engine sharing the exact same database file."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{test_db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def do_connect(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA synchronous = OFF")
        cursor.execute("PRAGMA journal_mode = MEMORY")
        cursor.close()
        dbapi_connection.create_function(
            "to_char",
            2,
            lambda dt, fmt: str(dt)[:10] if dt else "",
        )

    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(
    async_test_engine,
    sync_test_engine,
    monkeypatch,
) -> AsyncGenerator[AsyncSession, None]:
    """Yields an isolated asynchronous SQLAlchemy session and patches global factories."""
    import backend.database.session as session_mod
    import backend.main as main_mod

    test_sync_factory = sessionmaker(
        bind=sync_test_engine,
        class_=Session,
        expire_on_commit=False,
        autoflush=False,
    )
    test_async_factory = async_sessionmaker(
        bind=async_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    monkeypatch.setattr(session_mod, "sync_session_factory", test_sync_factory)
    monkeypatch.setattr(session_mod, "async_session_factory", test_async_factory)
    monkeypatch.setattr(session_mod, "AsyncSessionLocal", test_async_factory)
    monkeypatch.setattr(main_mod, "AsyncSessionLocal", test_async_factory)

    async with test_async_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def sync_db_session(sync_test_engine) -> Generator[Session, None, None]:
    """Yields an isolated synchronous SQLAlchemy session for Celery / runner testing."""
    session_factory = sessionmaker(
        bind=sync_test_engine,
        class_=Session,
        expire_on_commit=False,
        autoflush=False,
    )
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ------------------------------------------------------------------------------
# 3. Mock Redis Manager Fixture
# ------------------------------------------------------------------------------
@pytest.fixture
def mock_redis() -> MockRedisManager:
    """Yields a fresh in-memory mock Redis manager instance."""
    return MockRedisManager()


# ------------------------------------------------------------------------------
# 4. Pre-Seeded Identities & Staff Users
# ------------------------------------------------------------------------------
@pytest.fixture
async def seed_users(db_session: AsyncSession) -> Dict[str, StaffUser]:
    """
    Seeds standard staff users (admin, operator, inactive) into the test database.

    Returns:
        Dict mapping user roles to persisted StaffUser instances.
    """
    hashed_pwd = PRECOMPUTED_TEST_PASSWORD_HASH

    admin = StaffUser(
        email="admin@nirmauni.ac.in",
        name="Admin Coordinator",
        role="admin",
        password_hash=hashed_pwd,
        is_active=True,
    )
    operator = StaffUser(
        email="operator@nirmauni.ac.in",
        name="Operator Specialist",
        role="operator",
        password_hash=hashed_pwd,
        is_active=True,
    )
    inactive = StaffUser(
        email="inactive@nirmauni.ac.in",
        name="Suspended Account",
        role="operator",
        password_hash=hashed_pwd,
        is_active=False,
    )

    db_session.add_all([admin, operator, inactive])
    await db_session.commit()
    await db_session.refresh(admin)
    await db_session.refresh(operator)
    await db_session.refresh(inactive)

    return {"admin": admin, "operator": operator, "inactive": inactive}


@pytest.fixture
def admin_token(seed_users: Dict[str, StaffUser]) -> str:
    """Returns valid JWT access token for admin user."""
    admin = seed_users["admin"]
    return create_jwt_token(
        data={"sub": str(admin.id), "role": admin.role},
        expires_delta=datetime.timedelta(minutes=60),
    )


@pytest.fixture
def operator_token(seed_users: Dict[str, StaffUser]) -> str:
    """Returns valid JWT access token for operator user."""
    operator = seed_users["operator"]
    return create_jwt_token(
        data={"sub": str(operator.id), "role": operator.role},
        expires_delta=datetime.timedelta(minutes=60),
    )


@pytest.fixture
def inactive_token(seed_users: Dict[str, StaffUser]) -> str:
    """Returns valid JWT access token for inactive user."""
    inactive = seed_users["inactive"]
    return create_jwt_token(
        data={"sub": str(inactive.id), "role": inactive.role},
        expires_delta=datetime.timedelta(minutes=60),
    )


@pytest.fixture
def admin_headers(admin_token: str) -> Dict[str, str]:
    """Returns HTTP headers dictionary with admin Bearer token."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def operator_headers(operator_token: str) -> Dict[str, str]:
    """Returns HTTP headers dictionary with operator Bearer token."""
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture
def inactive_headers(inactive_token: str) -> Dict[str, str]:
    """Returns HTTP headers dictionary with inactive user Bearer token."""
    return {"Authorization": f"Bearer {inactive_token}"}


# ------------------------------------------------------------------------------
# 5. Pre-Seeded Students and Scripts
# ------------------------------------------------------------------------------
@pytest.fixture
async def seed_students(db_session: AsyncSession) -> List[Student]:
    """Seeds a representative cohort of students for filtering and campaign dispatch."""
    students = [
        Student(
            roll_number="21BCE001",
            name="Aarav Patel",
            phone="+919876500001",
            language_pref="hi",
            department="CS",
            semester=4,
            is_active=True,
        ),
        Student(
            roll_number="21BCE002",
            name="Diya Shah",
            phone="+919876500002",
            language_pref="gu",
            department="CS",
            semester=4,
            is_active=True,
        ),
        Student(
            roll_number="21BME003",
            name="Rohan Mehta",
            phone="+919876500003",
            language_pref="en",
            department="ME",
            semester=6,
            is_active=True,
        ),
        Student(
            roll_number="21BCE004",
            name="Sneha Joshi",
            phone="+919876500004",
            language_pref="hi",
            department="CS",
            semester=4,
            is_active=False,  # Inactive student
        ),
    ]
    db_session.add_all(students)
    await db_session.commit()
    for s in students:
        await db_session.refresh(s)
    return students


@pytest.fixture
async def seed_script(db_session: AsyncSession, seed_users: Dict[str, StaffUser]) -> CallScript:
    """Seeds an active call script template."""
    admin = seed_users["admin"]
    script = CallScript(
        name="Semester Fee Reminder — Hindi",
        category="fee_reminder",
        language="hi",
        system_prompt="You are a fee reminder voice assistant.",
        opening_message="Namaste, main Nirma University se automated assistant bol raha hoon.",
        is_active=True,
        created_by=admin.id,
    )
    db_session.add(script)
    await db_session.commit()
    await db_session.refresh(script)
    return script


# ------------------------------------------------------------------------------
# 6. Async HTTP Client with In-Memory Overrides
# ------------------------------------------------------------------------------
@pytest.fixture
async def async_client(
    db_session: AsyncSession,
    mock_redis: MockRedisManager,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Yields an AsyncClient bound to the FastAPI app with test session dependencies.
    """
    # Override database session dependency
    app.dependency_overrides[get_async_session] = lambda: db_session

    # Patch global webhook redis manager with mock redis
    import backend.telephony.webhook_handler as wh

    original_redis_mgr = wh.redis_manager
    original_redis_client = wh.redis_client
    wh.redis_manager = mock_redis
    wh.redis_client = mock_redis.get_client()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    # Cleanup overrides
    app.dependency_overrides.clear()
    wh.redis_manager = original_redis_mgr
    wh.redis_client = original_redis_client
