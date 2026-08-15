import os
import uuid
import json
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.auth import get_current_user
from core.config import settings
import models
from services.data_loader import load_dataframe
from services.profiler import clean_dataframe, build_profile

router = APIRouter(prefix="/datasets", tags=["datasets"])

ALLOWED_EXT = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json"}


@router.post("/upload")
async def upload_dataset(file: UploadFile = File(...), db: Session = Depends(get_db),
                          current_user: models.User = Depends(get_current_user)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'. Allowed: {ALLOWED_EXT}")

    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.MAX_UPLOAD_MB}MB limit.")

    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = os.path.join(settings.UPLOAD_DIR, stored_name)
    with open(stored_path, "wb") as f:
        f.write(contents)

    try:
        df = load_dataframe(stored_path, file.filename)
        clean_df, _log = clean_dataframe(df)
        profile = build_profile(clean_df)
    except Exception as e:
        os.remove(stored_path)
        raise HTTPException(status_code=422, detail=f"Could not parse file: {e}")

    # persist the CLEANED version so re-analysis is fast & consistent
    clean_path = stored_path + ".clean.parquet"
    clean_df.to_parquet(clean_path)

    dataset = models.Dataset(
        owner_id=current_user.id,
        filename=file.filename,
        stored_path=clean_path,
        file_type=ext,
        row_count=profile["n_rows"],
        col_count=profile["n_cols"],
        profile_json=json.dumps(profile, default=str),
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    return {"dataset_id": dataset.id, "filename": dataset.filename, "profile": profile}


@router.get("/")
def list_datasets(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    rows = db.query(models.Dataset).filter(models.Dataset.owner_id == current_user.id).all()
    return [{"id": d.id, "filename": d.filename, "row_count": d.row_count,
             "col_count": d.col_count, "created_at": d.created_at} for d in rows]


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: int, db: Session = Depends(get_db),
                    current_user: models.User = Depends(get_current_user)):
    ds = db.query(models.Dataset).filter(models.Dataset.id == dataset_id,
                                          models.Dataset.owner_id == current_user.id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if os.path.exists(ds.stored_path):
        os.remove(ds.stored_path)
    db.delete(ds)
    db.commit()
    return {"status": "deleted"}
