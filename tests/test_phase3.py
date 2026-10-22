import json
import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import StudentScore, ScoreSettings, InterventionAction, Student


def test_scores_and_risks_integrity():
    db: Session = SessionLocal()
    try:
        # Check settings
        settings = db.query(ScoreSettings).filter(ScoreSettings.key == "default").first()
        assert settings is not None
        total_w = (
            settings.weight_academic +
            settings.weight_attendance +
            settings.weight_placement +
            settings.weight_lms +
            settings.weight_skills
        )
        assert abs(total_w - 100.0) < 0.01, f"Weights sum to {total_w}, expected 100%"

        scores = db.query(StudentScore).all()
        assert len(scores) == 600, f"Expected 600 scores, got {len(scores)}"

        for s in scores:
            assert 0.0 <= s.total_success_score <= 100.0, f"Invalid total score: {s.total_success_score}"
            assert 0.0 <= s.academic_score <= 100.0
            assert 0.0 <= s.attendance_score <= 100.0
            assert 0.0 <= s.placement_score <= 100.0
            assert 0.0 <= s.lms_score <= 100.0
            assert 0.0 <= s.skills_feedback_score <= 100.0

            assert s.academic_risk_level in ["Low", "Medium", "High"]
            assert s.placement_risk_level in ["Low", "Medium", "High"]

            acad_reasons = json.loads(s.academic_risk_reasons)
            assert isinstance(acad_reasons, list)

            place_reasons = json.loads(s.placement_risk_reasons)
            assert isinstance(place_reasons, list)

            assert s.score_explanation is not None and len(s.score_explanation) > 10
            assert s.segment_rule in [
                "Stars",
                "High Academics / Low Placement Readiness",
                "Silent Strugglers",
                "Disengaging",
                "Steady Performers"
            ]
            assert s.segment_kmeans is not None and len(s.segment_kmeans) > 0
            assert 0.0 <= s.ml_risk_probability <= 1.0

        # Check interventions
        interventions = db.query(InterventionAction).all()
        assert len(interventions) > 0
        for action in interventions:
            assert action.potential_gain > 0
            assert action.urgency >= 1.0
            assert action.priority > 0
            assert action.status in ["pending", "in_progress", "done"]

    finally:
        db.close()
