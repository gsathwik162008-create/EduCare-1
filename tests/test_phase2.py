import os
import pandas as pd
import pytest
from sqlalchemy.orm import Session

from app.database import engine, SessionLocal
from app.models import Student, UnifiedStudentMetrics, CleaningLog, SemesterHistory, SubjectRecord
from app.ingestion import ingest_seven_sources


def test_seed_and_ingestion_integrity():
    db: Session = SessionLocal()
    try:
        # 1. Total students count
        total_students = db.query(Student).count()
        assert total_students == 600, f"Expected 600 students, got {total_students}"

        # 2. Total unified metrics count must match exactly
        total_metrics = db.query(UnifiedStudentMetrics).count()
        assert total_metrics == 600, f"Expected 600 unified metrics, got {total_metrics}"

        # 3. Check cleaning logs for injected mess types
        logs = db.query(CleaningLog).all()
        issue_types = set(log.issue_type for log in logs)
        print(f"Detected issue types: {issue_types}")
        assert "duplicate_id" in issue_types
        assert "missing_value" in issue_types
        assert "spelling_normalization" in issue_types
        assert "out_of_range" in issue_types
        assert "id_normalization" in issue_types

        # 4. Check that all departments are standardized
        depts = set(s.department for s in db.query(Student.department).distinct())
        expected_depts = {"CSE", "ECE", "EEE", "Mech", "Civil"}
        assert depts.issubset(expected_depts), f"Unexpected raw depts: {depts}"

        # 5. Semester history and subject records populated
        sem_count = db.query(SemesterHistory).count()
        subj_count = db.query(SubjectRecord).count()
        assert sem_count > 0
        assert subj_count > 0

    finally:
        db.close()


def test_reupload_does_not_duplicate():
    db: Session = SessionLocal()
    try:
        initial_count = db.query(Student).count()

        # Load academic CSV from data/
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        df_acad = pd.read_csv(os.path.join(data_dir, "academic.csv"))

        # Re-ingest academic
        result = ingest_seven_sources({"academic": df_acad}, db)
        assert result["status"] == "success"

        after_count = db.query(Student).count()
        assert after_count == initial_count, f"Student count changed from {initial_count} to {after_count} on re-upload!"
    finally:
        db.close()
