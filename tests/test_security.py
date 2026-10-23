import re

from fastapi.testclient import TestClient

from app import llm
from app.database import SessionLocal
from app.main import app
from app.models import (
    FacultyAssignment,
    InterventionAction,
    Student,
    StudentMentorMessage,
    StudentScore,
    User
)

client = TestClient(app)


def login(username, password):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_student_cannot_explain_another_students_profile():
    student_token = login("21CIV036", "student123")
    db = SessionLocal()
    try:
        other_student = db.query(Student).filter(Student.student_id != "21CIV036").first()
        assert other_student is not None
        other_student_id = other_student.student_id
    finally:
        db.close()

    response = client.post(
        "/api/explain",
        json={"student_id": other_student_id},
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert response.status_code == 403


def test_student_explanation_uses_supportive_strengths_and_focus_areas():
    student_token = login("21CIV036", "student123")

    response = client.post(
        "/api/explain",
        json={"student_id": "21CIV036"},
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert response.status_code == 200
    explanation = response.json()["explanation"]
    assert "Your strengths:" in explanation
    assert "Focus areas:" in explanation
    assert not any(
        term in explanation.lower()
        for term in ("risk", "need support", "backlog", "flag")
    )


def test_faculty_cannot_update_intervention_outside_their_cohort():
    faculty_token = login("prof_sharma", "faculty123")
    db = SessionLocal()
    try:
        faculty = db.query(User).filter(User.username == "prof_sharma").first()
        assert faculty is not None
        assigned_student_ids = db.query(FacultyAssignment.student_id).filter(
            FacultyAssignment.faculty_id == faculty.id
        )
        action = db.query(InterventionAction).join(Student).filter(
            Student.mentor_id != faculty.id,
            ~Student.student_id.in_(assigned_student_ids)
        ).first()
        assert action is not None
        action_id = action.id
        original_notes = action.notes
    finally:
        db.close()

    try:
        response = client.patch(
            f"/api/interventions/{action_id}",
            json={"notes": "Unauthorized cohort update attempt"},
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        assert response.status_code == 403
    finally:
        db = SessionLocal()
        try:
            action = db.query(InterventionAction).filter(InterventionAction.id == action_id).first()
            if action is not None:
                action.notes = original_notes
                db.commit()
        finally:
            db.close()


def test_faculty_can_update_intervention_in_their_cohort():
    faculty_token = login("prof_sharma", "faculty123")
    db = SessionLocal()
    try:
        faculty = db.query(User).filter(User.username == "prof_sharma").first()
        action = db.query(InterventionAction).join(Student).filter(
            Student.mentor_id == faculty.id
        ).first()
        assert faculty is not None
        assert action is not None
        action_id = action.id
        original_notes = action.notes
    finally:
        db.close()

    try:
        response = client.patch(
            f"/api/interventions/{action_id}",
            json={"notes": "Authorized cohort update"},
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        assert response.status_code == 200
    finally:
        db = SessionLocal()
        try:
            action = db.query(InterventionAction).filter(InterventionAction.id == action_id).first()
            if action is not None:
                action.notes = original_notes
                db.commit()
        finally:
            db.close()


def test_intervention_completion_records_score_outcome_and_hides_it_from_students():
    admin_token = login("admin", "admin123")
    db = SessionLocal()
    try:
        action = db.query(InterventionAction).filter(
            InterventionAction.status != "done"
        ).first()
        assert action is not None
        score = db.query(StudentScore).filter(
            StudentScore.student_id == action.student_id
        ).first()
        assert score is not None
        action_id = action.id
        student_id = action.student_id
        original_values = (
            action.status,
            action.score_at_creation,
            action.score_at_completion,
            action.completed_at,
        )
        expected_score = float(score.total_success_score)
        expected_creation_score = expected_score - 5.0
        action.score_at_creation = expected_creation_score
        db.commit()
    finally:
        db.close()

    try:
        completion_response = client.patch(
            f"/api/interventions/{action_id}",
            json={"status": "done"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert completion_response.status_code == 200

        admin_list = client.get(
            f"/api/interventions?status=all&student_id={student_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        completed_action = next(
            item for item in admin_list.json()["interventions"]
            if item["id"] == action_id
        )
        assert completed_action["score_at_creation"] == expected_creation_score
        assert completed_action["score_at_completion"] == expected_score
        assert completed_action["score_change"] == 5.0
        db = SessionLocal()
        try:
            persisted_action = db.query(InterventionAction).filter(
                InterventionAction.id == action_id
            ).first()
            assert persisted_action.completed_at is not None
        finally:
            db.close()

        student_token = login(student_id, "student123")
        student_list = client.get(
            f"/api/interventions?status=all",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        student_action = next(
            item for item in student_list.json()["interventions"]
            if item["id"] == action_id
        )
        assert "score_at_creation" not in student_action
        assert "score_at_completion" not in student_action
        assert "score_change" not in student_action
    finally:
        db = SessionLocal()
        try:
            action = db.query(InterventionAction).filter(
                InterventionAction.id == action_id
            ).first()
            if action is not None:
                action.status = original_values[0]
                action.score_at_creation = original_values[1]
                action.score_at_completion = original_values[2]
                action.completed_at = original_values[3]
                db.commit()
        finally:
            db.close()


def test_student_cannot_ask_for_campus_wide_analytics():
    student_token = login("21CIV036", "student123")

    response = client.post(
        "/api/ask",
        json={"query": "How many students are at high risk across the campus?"},
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert response.status_code == 403


def test_admin_can_ask_campus_analytics(monkeypatch):
    monkeypatch.setattr(llm, "LLM_API_KEY", "")
    admin_token = login("admin", "admin123")

    response = client.post(
        "/api/ask",
        json={"query": "How many students are at high risk?"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert response.json()["source"] == "keyword_synthesis"


def test_faculty_analytics_are_scoped_to_her_cohort(monkeypatch):
    monkeypatch.setattr(llm, "LLM_API_KEY", "")
    admin_token = login("admin", "admin123")
    faculty_token = login("prof_sharma", "faculty123")
    payload = {"query": "How many students are at high risk?"}

    admin_response = client.post(
        "/api/ask",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    faculty_response = client.post(
        "/api/ask",
        json=payload,
        headers={"Authorization": f"Bearer {faculty_token}"}
    )

    assert admin_response.status_code == 200
    assert faculty_response.status_code == 200
    admin_count = int(re.search(r"\d+", admin_response.json()["answer"]).group())
    faculty_count = int(re.search(r"\d+", faculty_response.json()["answer"]).group())
    assert faculty_count < admin_count


def test_authentication_token_in_query_parameter_is_rejected():
    student_token = login("21CIV036", "student123")

    response = client.get(
        "/api/students/21CIV036",
        params={"token": student_token}
    )

    assert response.status_code == 401


def test_faculty_cannot_reply_to_message_outside_their_cohort():
    faculty_token = login("prof_sharma", "faculty123")
    db = SessionLocal()
    try:
        faculty = db.query(User).filter(User.username == "prof_sharma").first()
        assert faculty is not None
        other_student = db.query(Student).filter(Student.mentor_id != faculty.id).first()
        assert other_student is not None

        message = StudentMentorMessage(
            student_id=other_student.student_id,
            mentor_id=other_student.mentor_id,
            message="Security test message"
        )
        db.add(message)
        db.commit()
        message_id = message.id
    finally:
        db.close()

    try:
        response = client.patch(
            f"/api/students/messages/{message_id}/reply",
            json={"reply": "Unauthorized reply attempt"},
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        assert response.status_code == 403
    finally:
        db = SessionLocal()
        try:
            message = db.query(StudentMentorMessage).filter(
                StudentMentorMessage.id == message_id
            ).first()
            if message is not None:
                db.delete(message)
                db.commit()
        finally:
            db.close()


def test_faculty_can_reply_to_message_in_their_cohort():
    faculty_token = login("prof_sharma", "faculty123")
    db = SessionLocal()
    try:
        faculty = db.query(User).filter(User.username == "prof_sharma").first()
        assert faculty is not None
        student = db.query(Student).filter(Student.mentor_id == faculty.id).first()
        assert student is not None

        message = StudentMentorMessage(
            student_id=student.student_id,
            mentor_id=faculty.id,
            message="Security test message"
        )
        db.add(message)
        db.commit()
        message_id = message.id
    finally:
        db.close()

    try:
        response = client.patch(
            f"/api/students/messages/{message_id}/reply",
            json={"reply": "Authorized cohort reply"},
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        assert response.status_code == 200
    finally:
        db = SessionLocal()
        try:
            message = db.query(StudentMentorMessage).filter(
                StudentMentorMessage.id == message_id
            ).first()
            if message is not None:
                db.delete(message)
                db.commit()
        finally:
            db.close()
