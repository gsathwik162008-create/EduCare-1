import io
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import User, ScoreSettings, CleaningLog, Student, StudentScore
from app.auth import get_current_user, require_role
from app.ingestion import ingest_seven_sources, CSV_TEMPLATES
from app.analytics_pipeline import run_full_analytics_pipeline
from app.ml import get_model_metrics

router = APIRouter(prefix="/api/admin", tags=["admin"])


class SettingsUpdate(BaseModel):
    weight_academic: float = Field(..., ge=0, le=100)
    weight_attendance: float = Field(..., ge=0, le=100)
    weight_placement: float = Field(..., ge=0, le=100)
    weight_lms: float = Field(..., ge=0, le=100)
    weight_skills: float = Field(..., ge=0, le=100)
    threshold_academic_cgpa: float = Field(..., ge=0, le=10)
    threshold_attendance_pct: float = Field(..., ge=0, le=100)
    threshold_coding_score: float = Field(..., ge=0, le=100)


@router.get("/settings")
def get_score_settings(
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Retrieve scoring weights and risk thresholds."""
    settings = db.query(ScoreSettings).filter(ScoreSettings.key == "default").first()
    if not settings:
        settings = ScoreSettings(key="default")
        db.add(settings)
        db.commit()

    return {
        "weight_academic": settings.weight_academic,
        "weight_attendance": settings.weight_attendance,
        "weight_placement": settings.weight_placement,
        "weight_lms": settings.weight_lms,
        "weight_skills": settings.weight_skills,
        "threshold_academic_cgpa": settings.threshold_academic_cgpa,
        "threshold_attendance_pct": settings.threshold_attendance_pct,
        "threshold_coding_score": settings.threshold_coding_score,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None
    }


@router.post("/settings")
def update_score_settings(
    payload: SettingsUpdate,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Update weights and thresholds; validates that weights sum to 100% and recomputes all scores."""
    total_weights = (
        payload.weight_academic +
        payload.weight_attendance +
        payload.weight_placement +
        payload.weight_lms +
        payload.weight_skills
    )
    if abs(total_weights - 100.0) > 0.05:
        raise HTTPException(
            status_code=400,
            detail=f"Score weights must sum to exactly 100%. Current sum: {total_weights:.1f}%"
        )

    settings = db.query(ScoreSettings).filter(ScoreSettings.key == "default").first()
    if not settings:
        settings = ScoreSettings(key="default")
        db.add(settings)

    settings.weight_academic = payload.weight_academic
    settings.weight_attendance = payload.weight_attendance
    settings.weight_placement = payload.weight_placement
    settings.weight_lms = payload.weight_lms
    settings.weight_skills = payload.weight_skills
    settings.threshold_academic_cgpa = payload.threshold_academic_cgpa
    settings.threshold_attendance_pct = payload.threshold_attendance_pct
    settings.threshold_coding_score = payload.threshold_coding_score
    settings.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Recompute analytics pipeline with new weights
    pipeline_res = run_full_analytics_pipeline(db)

    return {
        "status": "success",
        "message": "Weights updated and pipeline successfully recomputed",
        "pipeline_result": pipeline_res
    }


@router.post("/recompute")
def trigger_recompute(
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Admin trigger to recompute all scoring, risk flags, ML predictions, and interventions."""
    result = run_full_analytics_pipeline(db)
    return {"status": "success", "result": result}


@router.post("/upload")
async def upload_csv_files(
    academic: Optional[UploadFile] = File(None),
    attendance: Optional[UploadFile] = File(None),
    lms: Optional[UploadFile] = File(None),
    engagement: Optional[UploadFile] = File(None),
    placement: Optional[UploadFile] = File(None),
    skills: Optional[UploadFile] = File(None),
    feedback: Optional[UploadFile] = File(None),
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Screen 8: Ingestion upload endpoint for any combination of the 7 CSV files.
    Performs validation, cleaning, deduplication, logging, and pipeline recompute.
    """
    file_map = {
        "academic": academic,
        "attendance": attendance,
        "lms": lms,
        "engagement": engagement,
        "placement": placement,
        "skills": skills,
        "feedback": feedback
    }

    uploaded_dfs = {}
    for name, f in file_map.items():
        if f is not None and f.filename:
            content = await f.read()
            if content:
                try:
                    df = pd.read_csv(io.BytesIO(content))
                    uploaded_dfs[name] = df
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Failed to parse CSV file '{f.filename}': {str(e)}")

    if not uploaded_dfs:
        raise HTTPException(status_code=400, detail="Please upload at least one valid CSV file.")

    res = ingest_seven_sources(uploaded_dfs, db)
    if res.get("status") == "error":
        return Response(status_code=400, content=res.get("message", "Validation failed"))

    # Automatically recompute analytics
    pipeline_res = run_full_analytics_pipeline(db)

    return {
        "status": "success",
        "ingestion_summary": res,
        "pipeline_summary": pipeline_res
    }


@router.get("/quality-log")
def get_data_quality_log(
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Screen 8: Data Quality Screen showing issues grouped by type, before/after counts, and detailed log."""
    logs = db.query(CleaningLog).order_by(CleaningLog.timestamp.desc()).all()

    issue_counts = {}
    source_counts = {}
    for l in logs:
        issue_counts[l.issue_type] = issue_counts.get(l.issue_type, 0) + 1
        source_counts[l.source_file] = source_counts.get(l.source_file, 0) + 1

    issue_breakdown = [
        {"issue_type": k, "count": v}
        for k, v in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    source_breakdown = [
        {"source_file": k, "count": v}
        for k, v in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    recent_entries = [
        {
            "id": l.id,
            "timestamp": l.timestamp.isoformat() if l.timestamp else None,
            "source_file": l.source_file,
            "row_number": l.row_number,
            "student_id": l.student_id,
            "field_name": l.field_name,
            "issue_type": l.issue_type,
            "original_value": l.original_value,
            "cleaned_value": l.cleaned_value,
            "rule_applied": l.rule_applied
        }
        for l in logs[:100]
    ]

    return {
        "total_anomalies_cleaned": len(logs),
        "issue_breakdown": issue_breakdown,
        "source_breakdown": source_breakdown,
        "recent_logs": recent_entries
    }


@router.get("/templates/{source_name}")
def download_csv_template(
    source_name: str,
    current_user: User = Depends(require_role(["ADMIN"]))
):
    """Download standardized CSV template for any of the 7 sources."""
    src = source_name.lower().strip()
    if src not in CSV_TEMPLATES:
        raise HTTPException(status_code=404, detail=f"Template '{source_name}' not found. Available: {list(CSV_TEMPLATES.keys())}")

    content = CSV_TEMPLATES[src]
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=template_{src}.csv"}
    )


@router.get("/model-metrics")
def get_ml_model_metrics(
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    """Screen 9: Gradient Boosting 5-fold cross-validated metrics and feature importances."""
    metrics = get_model_metrics()
    return metrics
