from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import FacultyAssignment, InterventionAction, Student, StudentMentorMessage, User

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
        assigned_student_ids = db.query(FacultyAssignment.student_id).filter(
            FacultyAssignment.faculty_id == faculty.id
        )
        action = db.query(InterventionAction).join(Student).filter(
            ~Student.student_id.in_(assigned_student_ids)
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


def test_student_cannot_ask_for_campus_wide_analytics():
    student_token = login("21CIV036", "student123")

    response = client.post(
        "/api/ask",
        json={"query": "How many students are at high risk across the campus?"},
        headers={"Authorization": f"Bearer {student_token}"}
    )

    assert response.status_code == 403


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
        other_student = db.query(Student).filter(Student.mentor_id != faculty.id).first()
        assert faculty is not None
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
