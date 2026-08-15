from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_lightweight_migrations():
    """`Base.metadata.create_all` creates the new `chat_sessions` table fine,
    but SQLite's create_all never adds columns to a table that already
    exists — so existing `chat_messages` rows (saved before session support)
    would be missing `session_id`. This adds that column if absent and
    backfills a "New Chat" session per dataset so old conversations keep
    showing up in chat history instead of vanishing."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "chat_messages" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("chat_messages")}
    with engine.begin() as conn:
        if "session_id" not in existing:
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN session_id INTEGER"))
        orphans = conn.execute(text("SELECT DISTINCT dataset_id FROM chat_messages WHERE session_id IS NULL")).fetchall()
        for (dataset_id,) in orphans:
            row = conn.execute(
                text("INSERT INTO chat_sessions (dataset_id, title, created_at, updated_at) "
                     "VALUES (:did, 'Previous Chat', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
                {"did": dataset_id},
            )
            new_session_id = row.lastrowid
            conn.execute(
                text("UPDATE chat_messages SET session_id = :sid WHERE dataset_id = :did AND session_id IS NULL"),
                {"sid": new_session_id, "did": dataset_id},
            )
