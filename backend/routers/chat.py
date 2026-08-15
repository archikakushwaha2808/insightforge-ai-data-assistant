import json
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from core.database import get_db
from core.auth import get_current_user
import models
from services.groq_service import chat as groq_chat, AssistantTimeoutError, AssistantOverloadedError

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


def _get_dataset_or_404(dataset_id: int, db: Session, user: models.User) -> models.Dataset:
    ds = db.query(models.Dataset).filter(models.Dataset.id == dataset_id,
                                          models.Dataset.owner_id == user.id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


def _get_session_or_404(session_id: int, db: Session, user: models.User) -> models.ChatSession:
    session = db.query(models.ChatSession).join(models.Dataset) \
        .filter(models.ChatSession.id == session_id, models.Dataset.owner_id == user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return session


def _load_list(raw: "str | None") -> list:
    """chart_json/table_json store a JSON *list* (multi-query turns keep every
    result). Older rows saved before that change may still hold a single JSON
    object — wrap those in a list so history keeps rendering correctly."""
    if not raw:
        return []
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, list) else [parsed]


def _serialize_message(m: models.ChatMessage) -> dict:
    charts = _load_list(m.chart_json)
    tables = _load_list(m.table_json)
    return {
        "role": m.role, "content": m.content,
        "chart": charts[0] if charts else None,
        "charts": charts,
        "table": tables[0] if tables else None,
        "tables": tables,
        "created_at": m.created_at,
    }


# ---------------------------------------------------------------------------
# Sessions — a ChatGPT-style "New Chat" / history list, scoped to a dataset.
# ---------------------------------------------------------------------------

@router.get("/{dataset_id}/sessions")
def list_sessions(dataset_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    ds = _get_dataset_or_404(dataset_id, db, current_user)
    sessions = db.query(models.ChatSession).filter(models.ChatSession.dataset_id == ds.id) \
        .order_by(models.ChatSession.updated_at.desc()).all()
    return [{"id": s.id, "title": s.title, "created_at": s.created_at, "updated_at": s.updated_at} for s in sessions]


@router.post("/{dataset_id}/sessions")
def create_session(dataset_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """'+ New Chat' — a genuinely fresh conversation/session. Nothing from any
    other session is ever sent to the model for this session's messages."""
    ds = _get_dataset_or_404(dataset_id, db, current_user)
    session = models.ChatSession(dataset_id=ds.id, title="New Chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id, "title": session.title, "created_at": session.created_at, "updated_at": session.updated_at}


@router.get("/sessions/{session_id}/history")
def get_session_history(session_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    session = _get_session_or_404(session_id, db, current_user)
    msgs = db.query(models.ChatMessage).filter(models.ChatMessage.session_id == session.id) \
        .order_by(models.ChatMessage.created_at).all()
    return [_serialize_message(m) for m in msgs]


@router.post("/sessions/{session_id}/message")
def send_session_message(session_id: int, payload: ChatRequest, db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    session = _get_session_or_404(session_id, db, current_user)
    ds = db.query(models.Dataset).filter(models.Dataset.id == session.dataset_id).first()
    profile = json.loads(ds.profile_json)

    prior = db.query(models.ChatMessage).filter(models.ChatMessage.session_id == session.id) \
        .order_by(models.ChatMessage.created_at).all()
    history = [{"role": m.role, "content": m.content} for m in prior]

    try:
        df = pd.read_parquet(ds.stored_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load dataset: {e}")

    try:
        result = groq_chat(profile, history, payload.message, df)
    except AssistantTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Assistant timed out: {e}")
    except AssistantOverloadedError as e:
        # Friendly, actionable message for 413 (too large)/429 (rate limit) —
        # never the raw Groq error text.
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI assistant failed: {e}")

    charts = result.get("charts") or ([result["chart"]] if result.get("chart") else [])
    tables = result.get("tables") or ([result["table"]] if result.get("table") else [])

    user_msg = models.ChatMessage(dataset_id=ds.id, session_id=session.id, role="user", content=payload.message)
    assistant_msg = models.ChatMessage(
        dataset_id=ds.id, session_id=session.id, role="assistant", content=result["reply"],
        chart_json=json.dumps(charts) if charts else None,
        table_json=json.dumps(tables) if tables else None,
    )
    db.add(user_msg)
    db.add(assistant_msg)

    # Auto-title the session from the first message, ChatGPT-style — only
    # once, so re-opening an old conversation never renames it.
    if session.title == "New Chat":
        session.title = payload.message.strip()[:60] or "New Chat"
    from datetime import datetime
    session.updated_at = datetime.utcnow()
    db.add(session)
    db.commit()

    return {
        "session_id": session.id,
        "session_title": session.title,
        "reply": result["reply"],
        "chart": charts[0] if charts else None,
        "charts": charts,
        "kpis": result.get("kpis"),
        "table": tables[0] if tables else None,
        "tables": tables,
        "suggestions": result.get("suggestions", []),
    }


# ---------------------------------------------------------------------------
# Backward-compatible dataset-level endpoints — resolve to (or create) that
# dataset's most recently updated session, so nothing that already depends
# on the old flat per-dataset chat breaks.
# ---------------------------------------------------------------------------

def _latest_or_new_session(ds: models.Dataset, db: Session) -> models.ChatSession:
    session = db.query(models.ChatSession).filter(models.ChatSession.dataset_id == ds.id) \
        .order_by(models.ChatSession.updated_at.desc()).first()
    if session:
        return session
    session = models.ChatSession(dataset_id=ds.id, title="New Chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/{dataset_id}/history")
def get_history(dataset_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    ds = _get_dataset_or_404(dataset_id, db, current_user)
    session = _latest_or_new_session(ds, db)
    return get_session_history(session.id, db, current_user)


@router.post("/{dataset_id}/message")
def send_message(dataset_id: int, payload: ChatRequest, db: Session = Depends(get_db),
                  current_user: models.User = Depends(get_current_user)):
    ds = _get_dataset_or_404(dataset_id, db, current_user)
    session = _latest_or_new_session(ds, db)
    return send_session_message(session.id, payload, db, current_user)
