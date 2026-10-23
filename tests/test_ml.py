from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.ml import predict_student_risk_probability, train_gradient_boosting_model
from app.models import SemesterHistory

client = TestClient(app)


def login_admin():
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def train_model_from_database():
    db = SessionLocal()
    try:
        histories = db.query(SemesterHistory).all()
        metrics = train_gradient_boosting_model(histories)
        assert metrics["status"] == "trained"
        return histories, metrics
    finally:
        db.close()


def test_next_semester_model_trains_and_persists():
    _, metrics = train_model_from_database()

    assert metrics["training_samples"] > 0
    assert metrics["test_samples"] > 0
    assert set(metrics["model_metrics"]) == {"accuracy", "precision", "recall", "f1", "roc_auc"}
    assert set(metrics["baseline_majority_metrics"]) == {"accuracy", "precision", "recall", "f1", "roc_auc"}
    assert set(metrics["baseline_gpa_rule_metrics"]) == {"accuracy", "precision", "recall", "f1", "roc_auc"}


def test_model_metrics_endpoint_reports_honest_comparison():
    train_model_from_database()
    token = login_admin()

    response = client.get(
        "/api/admin/model-metrics",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    metrics = response.json()
    assert isinstance(metrics["model_beats_baseline"], bool)
    assert "Predicts next-semester GPA drop" in metrics["honest_note"]
    assert "model_metrics" in metrics
    assert "baseline_majority_metrics" in metrics
    assert "baseline_gpa_rule_metrics" in metrics


def test_prediction_returns_probability_between_zero_and_one():
    histories, _ = train_model_from_database()
    student_history = [row for row in histories if row.student_id == histories[0].student_id]

    prediction = predict_student_risk_probability(student_history)

    assert isinstance(prediction, float)
    assert 0.0 <= prediction <= 1.0
