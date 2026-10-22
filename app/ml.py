from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.inspection import permutation_importance
from sqlalchemy.orm import Session

from app.models import UnifiedStudentMetrics

FEATURE_NAMES = [
    "cgpa",
    "total_backlogs",
    "attendance_pct",
    "assignments_submitted_pct",
    "coding_score",
    "aptitude_score",
    "technical_skills_score",
    "mock_interviews_completed",
    "lms_login_count"
]

DISPLAY_FEATURE_NAMES = [
    "CGPA",
    "Backlog Count",
    "Attendance %",
    "Assignment Submission %",
    "Coding Score",
    "Aptitude Score",
    "Technical Skills",
    "Mock Interviews",
    "LMS Activity"
]

# Global cache for trained model and validation metrics
_TRAINED_MODEL: Optional[GradientBoostingClassifier] = None
_MODEL_METRICS: Dict[str, Any] = {}


def train_gradient_boosting_model(metrics_list: List[UnifiedStudentMetrics]) -> Dict[str, Any]:
    """
    Trains a Gradient Boosting Risk Classifier with 5-fold Cross-Validation.
    Target: 1 if student has high risk (cgpa < 6.0, attendance < 75%, backlogs >= 2, or coding < 40), 0 otherwise.
    """
    global _TRAINED_MODEL, _MODEL_METRICS

    if not metrics_list or len(metrics_list) < 20:
        return {
            "status": "insufficient_data",
            "cv_accuracy": 0.0,
            "cv_precision": 0.0,
            "cv_recall": 0.0,
            "cv_f1": 0.0,
            "cv_roc_auc": 0.0,
            "feature_importances": []
        }

    X_data = []
    y_data = []

    for m in metrics_list:
        cgpa = float(m.cgpa or 0.0)
        att = float(m.attendance_pct or 0.0)
        backlogs = int(m.total_backlogs or 0)
        code = float(m.coding_score or 0.0)
        assigns = float(m.assignments_submitted_pct or 0.0)
        apt = float(m.aptitude_score or 0.0)
        tech = float(m.technical_skills_score or 0.0)
        mocks = int(m.mock_interviews_completed or 0)
        logins = int(m.lms_login_count or 0)

        # Ground truth proxy for early warning risk model
        is_at_risk = 1 if (cgpa < 6.0 or att < 75.0 or backlogs >= 2 or code < 40.0) else 0

        X_data.append([
            cgpa, backlogs, att, assigns, code, apt, tech, mocks, logins
        ])
        y_data.append(is_at_risk)

    X = np.array(X_data)
    y = np.array(y_data)

    # Gradient Boosting Classifier
    clf = GradientBoostingClassifier(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        random_state=42
    )

    # 5-fold Stratified Cross-Validation
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scoring = ["accuracy", "precision", "recall", "f1", "roc_auc"]
    cv_results = cross_validate(clf, X, y, cv=skf, scoring=scoring)

    # Fit final model on all data
    clf.fit(X, y)
    _TRAINED_MODEL = clf

    # Feature importances
    raw_importances = clf.feature_importances_
    sorted_idx = np.argsort(raw_importances)[::-1]
    feature_importances = []
    for idx in sorted_idx:
        feature_importances.append({
            "feature": DISPLAY_FEATURE_NAMES[idx],
            "raw_key": FEATURE_NAMES[idx],
            "importance": round(float(raw_importances[idx]), 4),
            "percentage": round(float(raw_importances[idx]) * 100, 1)
        })

    _MODEL_METRICS = {
        "status": "trained",
        "training_samples": len(X),
        "cv_folds": 5,
        "cv_accuracy": round(float(np.mean(cv_results["test_accuracy"])), 4),
        "cv_precision": round(float(np.mean(cv_results["test_precision"])), 4),
        "cv_recall": round(float(np.mean(cv_results["test_recall"])), 4),
        "cv_f1": round(float(np.mean(cv_results["test_f1"])), 4),
        "cv_roc_auc": round(float(np.mean(cv_results["test_roc_auc"])), 4),
        "feature_importances": feature_importances,
        "model_type": "GradientBoostingClassifier (scikit-learn)"
    }

    return _MODEL_METRICS


def get_model_metrics() -> Dict[str, Any]:
    """Returns cached validation metrics or placeholder if not yet trained."""
    return _MODEL_METRICS if _MODEL_METRICS else {
        "status": "not_trained",
        "cv_accuracy": 0.0,
        "cv_precision": 0.0,
        "cv_recall": 0.0,
        "cv_f1": 0.0,
        "cv_roc_auc": 0.0,
        "feature_importances": []
    }


def predict_student_risk_probability(m: UnifiedStudentMetrics) -> float:
    """Predicts risk probability for a student using trained model."""
    global _TRAINED_MODEL
    if _TRAINED_MODEL is None:
        # Fallback rule-based probability estimate
        risk_pts = 0
        if float(m.cgpa or 0) < 6.0: risk_pts += 30
        if float(m.attendance_pct or 0) < 75.0: risk_pts += 30
        if int(m.total_backlogs or 0) >= 2: risk_pts += 25
        if float(m.coding_score or 0) < 40.0: risk_pts += 15
        return round(min(1.0, max(0.05, risk_pts / 100.0)), 2)

    features = np.array([[
        float(m.cgpa or 0.0),
        int(m.total_backlogs or 0),
        float(m.attendance_pct or 0.0),
        float(m.assignments_submitted_pct or 0.0),
        float(m.coding_score or 0.0),
        float(m.aptitude_score or 0.0),
        float(m.technical_skills_score or 0.0),
        int(m.mock_interviews_completed or 0),
        int(m.lms_login_count or 0)
    ]])

    try:
        prob = _TRAINED_MODEL.predict_proba(features)[0][1]
        return round(float(prob), 3)
    except Exception:
        return 0.15
