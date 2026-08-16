import io
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
from services import object_storage

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _get_dataset_or_404(dataset_id: int, db: Session, user: models.User) -> models.Dataset:
    ds = db.query(models.Dataset).filter(models.Dataset.id == dataset_id,
                                          models.Dataset.owner_id == user.id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


def _load_df(ds: models.Dataset) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(object_storage.download_bytes(ds.stored_path)))


@router.get("/{dataset_id}/dashboard")
def dashboard(dataset_id: int, filter_column: Optional[str] = None, filter_value: Optional[str] = None,
              db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
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
    ds = _get_dataset_or_404(dataset_id, db, current_user)
    profile = json.loads(ds.profile_json)
    try:
        return generate_business_insights(profile)
    except AssistantTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"AI insights timed out: {e}")
    except AssistantOverloadedError as e:
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