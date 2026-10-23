from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sqlalchemy.orm import Session

from app.models import SemesterHistory

FEATURE_NAMES = [
    "last_gpa",
    "gpa_change",
    "mean_attendance",
    "total_backlogs_so_far",
    "credits_earned_k"
]

DISPLAY_FEATURE_NAMES = [
    "Latest GPA",
    "GPA Change",
    "Mean Attendance",
    "Backlogs So Far",
    "Credits Earned"
]

MODEL_PATH = Path(__file__).resolve().parent.parent / "model_cache" / "risk_model.joblib"
_TRAINED_MODEL: Optional[GradientBoostingClassifier] = None
_MODEL_METRICS: Dict[str, Any] = {}


def _features_at_semester(history: Sequence[SemesterHistory], index: int) -> List[float]:
    current = history[index]
    previous_gpa = 0.0
    if current.semester > 1 and index > 0:
        previous = history[index - 1]
        if previous.semester == current.semester - 1:
            previous_gpa = float(previous.gpa or 0.0)

    rows_to_date = history[:index + 1]
    return [
        float(current.gpa or 0.0),
        float(current.gpa or 0.0) - previous_gpa if current.semester > 1 else 0.0,
        float(np.mean([float(row.attendance_pct or 0.0) for row in rows_to_date])),
        float(sum(int(row.backlogs or 0) for row in rows_to_date)),
        float(current.credits_earned or 0.0)
    ]


def _transition_examples(
    histories: Sequence[SemesterHistory]
) -> Tuple[List[List[float]], List[int], List[int]]:
    histories_by_student: Dict[str, List[SemesterHistory]] = {}
    for history in histories:
        histories_by_student.setdefault(history.student_id, []).append(history)

    features: List[List[float]] = []
    labels: List[int] = []
    transition_semesters: List[int] = []

    for student_history in histories_by_student.values():
        student_history.sort(key=lambda row: row.semester)
        for index in range(len(student_history) - 1):
            current = student_history[index]
            following = student_history[index + 1]
            if following.semester != current.semester + 1:
                continue

            features.append(_features_at_semester(student_history, index))
            labels.append(int(
                float(following.gpa or 0.0) < float(current.gpa or 0.0) - 0.5
                or int(following.backlogs or 0) > int(current.backlogs or 0)
            ))
            transition_semesters.append(current.semester)

    return features, labels, transition_semesters


def _classification_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
    probabilities: np.ndarray
) -> Dict[str, float]:
    try:
        roc_auc = float(roc_auc_score(actual, probabilities))
    except ValueError:
        roc_auc = 0.5

    return {
        "accuracy": round(float(accuracy_score(actual, predicted)), 4),
        "precision": round(float(precision_score(actual, predicted, zero_division=0)), 4),
        "recall": round(float(recall_score(actual, predicted, zero_division=0)), 4),
        "f1": round(float(f1_score(actual, predicted, zero_division=0)), 4),
        "roc_auc": round(roc_auc, 4)
    }


def _empty_metrics(status: str) -> Dict[str, Any]:
    zeros = {name: 0.0 for name in ("accuracy", "precision", "recall", "f1", "roc_auc")}
    return {
        "status": status,
        "training_samples": 0,
        "test_samples": 0,
        "accuracy": 0.0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "roc_auc": 0.0,
        "cv_accuracy": 0.0,
        "cv_precision": 0.0,
        "cv_recall": 0.0,
        "cv_f1": 0.0,
        "cv_roc_auc": 0.0,
        "model_metrics": zeros,
        "baseline_majority_metrics": zeros,
        "baseline_gpa_rule_metrics": zeros,
        "model_beats_baseline": False,
        "honest_note": "Model is not trained: insufficient semester transitions for a time-based evaluation.",
        "feature_importances": [],
        "model_type": "GradientBoostingClassifier (scikit-learn)"
    }


def train_gradient_boosting_model(histories: List[SemesterHistory]) -> Dict[str, Any]:
    """Train on early semester transitions and evaluate only on semesters 6->7 and 7->8."""
    global _TRAINED_MODEL, _MODEL_METRICS

    features, labels, semesters = _transition_examples(histories)
    train_indices = [i for i, semester in enumerate(semesters) if semester <= 5]
    test_indices = [i for i, semester in enumerate(semesters) if semester in (6, 7)]

    if not train_indices or not test_indices:
        _TRAINED_MODEL = None
        _MODEL_METRICS = _empty_metrics("insufficient_data")
        return _MODEL_METRICS

    X = np.asarray(features, dtype=float)
    y = np.asarray(labels, dtype=int)
    X_train, y_train = X[train_indices], y[train_indices]
    X_test, y_test = X[test_indices], y[test_indices]

    if len(np.unique(y_train)) < 2:
        _TRAINED_MODEL = None
        _MODEL_METRICS = _empty_metrics("insufficient_class_variation")
        _MODEL_METRICS["training_samples"] = len(train_indices)
        _MODEL_METRICS["test_samples"] = len(test_indices)
        _MODEL_METRICS["honest_note"] = (
            "Model is not trained: the time-based training transitions contain only one target class."
        )
        return _MODEL_METRICS

    model = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=2,
        learning_rate=0.05,
        random_state=42
    )
    model.fit(X_train, y_train)

    model_predictions = model.predict(X_test)
    model_probabilities = model.predict_proba(X_test)[:, 1]
    model_metrics = _classification_metrics(y_test, model_predictions, model_probabilities)

    majority_class = int(np.bincount(y_train).argmax())
    majority_predictions = np.full(len(y_test), majority_class)
    majority_probabilities = np.full(len(y_test), float(majority_class))
    majority_metrics = _classification_metrics(y_test, majority_predictions, majority_probabilities)

    gpa_rule_predictions = (X_test[:, 0] < 6.5).astype(int)
    gpa_rule_metrics = _classification_metrics(
        y_test,
        gpa_rule_predictions,
        gpa_rule_predictions.astype(float)
    )

    model_beats_baseline = (
        model_metrics["f1"] > majority_metrics["f1"]
        and model_metrics["f1"] > gpa_rule_metrics["f1"]
    )
    if model_beats_baseline:
        honest_note = (
            "Predicts next-semester GPA drop using a time-based train/test split on semester history. "
            "Its test F1 exceeds both baseline F1 scores."
        )
    else:
        honest_note = (
            "Predicts next-semester GPA drop using a time-based train/test split on semester history. "
            "The model does not beat both baselines on test F1."
        )

    feature_importances = [
        {
            "feature": display_name,
            "raw_key": feature_name,
            "importance": round(float(importance), 4),
            "percentage": round(float(importance) * 100, 1)
        }
        for feature_name, display_name, importance in zip(
            FEATURE_NAMES,
            DISPLAY_FEATURE_NAMES,
            model.feature_importances_
        )
    ]

    _MODEL_METRICS = {
        "status": "trained",
        "training_samples": len(train_indices),
        "test_samples": len(test_indices),
        "accuracy": model_metrics["accuracy"],
        "precision": model_metrics["precision"],
        "recall": model_metrics["recall"],
        "f1": model_metrics["f1"],
        "roc_auc": model_metrics["roc_auc"],
        "cv_accuracy": model_metrics["accuracy"],
        "cv_precision": model_metrics["precision"],
        "cv_recall": model_metrics["recall"],
        "cv_f1": model_metrics["f1"],
        "cv_roc_auc": model_metrics["roc_auc"],
        "model_metrics": model_metrics,
        "baseline_majority_metrics": majority_metrics,
        "baseline_gpa_rule_metrics": gpa_rule_metrics,
        "model_beats_baseline": model_beats_baseline,
        "honest_note": honest_note,
        "feature_importances": feature_importances,
        "model_type": "GradientBoostingClassifier (scikit-learn)"
    }
    _TRAINED_MODEL = model

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "metrics": _MODEL_METRICS}, MODEL_PATH)
    return _MODEL_METRICS


def get_model_metrics() -> Dict[str, Any]:
    """Return cached test metrics, including a clear note before training."""
    return _MODEL_METRICS if _MODEL_METRICS else _empty_metrics("not_trained")


def _load_cached_model() -> None:
    global _TRAINED_MODEL, _MODEL_METRICS
    if not MODEL_PATH.is_file():
        return

    cached = joblib.load(MODEL_PATH)
    if not isinstance(cached, dict) or "model" not in cached or "metrics" not in cached:
        raise ValueError(f"Invalid persisted risk model format at {MODEL_PATH}")
    _TRAINED_MODEL = cached["model"]
    _MODEL_METRICS = cached["metrics"]


def predict_student_risk_probability(history: Sequence[SemesterHistory]) -> float:
    """Predict next-semester GPA-drop risk from the student's latest history features."""
    if _TRAINED_MODEL is None or not history:
        return 0.0

    ordered_history = sorted(history, key=lambda row: row.semester)
    features = np.asarray(
        [_features_at_semester(ordered_history, len(ordered_history) - 1)],
        dtype=float
    )
    return round(float(_TRAINED_MODEL.predict_proba(features)[0][1]), 3)


_load_cached_model()
