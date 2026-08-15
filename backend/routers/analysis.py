import json
from typing import Optional
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.auth import get_current_user
import models
from services.eda import generate_eda_charts, compute_kpis
from services.profiler import build_profile
from services.ml_pipeline import run_supervised, run_unsupervised
from services.groq_service import generate_business_insights, AssistantTimeoutError, AssistantOverloadedError

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _get_dataset_or_404(dataset_id: int, db: Session, user: models.User) -> models.Dataset:
    ds = db.query(models.Dataset).filter(models.Dataset.id == dataset_id,
                                          models.Dataset.owner_id == user.id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


def _load_df(ds: models.Dataset) -> pd.DataFrame:
    return pd.read_parquet(ds.stored_path)


@router.get("/{dataset_id}/dashboard")
def dashboard(dataset_id: int, filter_column: Optional[str] = None, filter_value: Optional[str] = None,
              db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Power-BI-style dashboard: KPI cards + a coordinated grid of charts,
    built directly from the dataset (never from chatbot chart output). When
    filter_column/filter_value are given (a slicer selection), KPIs and
    charts are recomputed over just the matching rows so the dashboard
    responds to the filter, while `profile` always reflects the FULL
    dataset so filter dropdown options stay stable as the user filters."""
    ds = _get_dataset_or_404(dataset_id, db, current_user)
    profile = json.loads(ds.profile_json)
    df = _load_df(ds)

    filtered_df = df
    active_profile = profile
    if filter_column and filter_column in df.columns and filter_value not in (None, "", "__all__"):
        mask = df[filter_column].astype(str) == str(filter_value)
        candidate = df[mask]
        if len(candidate) > 0:
            filtered_df = candidate
            active_profile = build_profile(filtered_df)

    charts = generate_eda_charts(filtered_df, active_profile)
    kpis = compute_kpis(filtered_df, active_profile)
    return {
        "profile": profile,
        "kpis": kpis,
        "charts": charts,
        "filtered_row_count": int(len(filtered_df)),
        "filters_applied": bool(filtered_df is not df),
        "filterable_columns": profile.get("categorical_columns", []) + profile.get("datetime_columns", []),
    }


@router.get("/{dataset_id}/insights")
def insights(dataset_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Stateless every time: reloads the dataset's profile fresh from the DB
    and calls generate_business_insights() with no memory of any prior
    request, so a page refresh or "Try again" click always issues a brand
    new, independent Groq request rather than building on a previous one."""
    ds = _get_dataset_or_404(dataset_id, db, current_user)
    profile = json.loads(ds.profile_json)
    try:
        return generate_business_insights(profile)
    except AssistantTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"AI insights timed out: {e}")
    except AssistantOverloadedError as e:
        # Covers Groq 413 (request too large) and 429 (rate limited) with the
        # friendly, actionable message already built in groq_service.
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI insights failed: {e}")


@router.post("/{dataset_id}/ml")
def run_ml(dataset_id: int, target_column: Optional[str] = None,
           db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    ds = _get_dataset_or_404(dataset_id, db, current_user)
    profile = json.loads(ds.profile_json)
    df = _load_df(ds)

    if target_column:
        if target_column not in df.columns:
            raise HTTPException(status_code=400, detail=f"Column '{target_column}' not found.")
        return run_supervised(df, target_column)
    else:
        return run_unsupervised(df, profile["numeric_columns"])
