from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import FacultyAssignment, Student, StudentMentorMessage, User


client = TestClient(app)


def login(username, password):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_message(student_id, text, created_at):
    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.student_id == student_id).first()
        assert student is not None
        message = StudentMentorMessage(
            student_id=student_id,
            mentor_id=student.mentor_id,
            message=text,
            status="open",
            created_at=created_at
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message.id
    finally:
        db.close()


def delete_messages(message_ids):
    db = SessionLocal()
    try:
        db.query(StudentMentorMessage).filter(
            StudentMentorMessage.id.in_(message_ids)
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def faculty_students():
    db = SessionLocal()
    try:
        faculty = db.query(User).filter(User.username == "prof_sharma").first()
        assert faculty is not None
        assigned_ids = db.query(FacultyAssignment.student_id).filter(
            FacultyAssignment.faculty_id == faculty.id
        )
        cohort_student = db.query(Student).filter(
            (Student.mentor_id == faculty.id)
            | Student.student_id.in_(assigned_ids)
        ).first()
        outside_student = db.query(Student).filter(
            Student.mentor_id != faculty.id,
            ~Student.student_id.in_(assigned_ids)
        ).first()
        assert cohort_student is not None
        assert outside_student is not None
        return cohort_student.student_id, outside_student.student_id
    finally:
        db.close()


def test_admin_sees_all_open_messages():
    admin_headers = login("admin", "admin123")
    cohort_student_id, outside_student_id = faculty_students()
    created_at = datetime.utcnow()
    message_ids = [
        create_message(cohort_student_id, "Admin inbox cohort test", created_at),
        create_message(outside_student_id, "Admin inbox outside test", created_at + timedelta(seconds=1))
    ]
    try:
        response = client.get("/api/students/messages/inbox", headers=admin_headers)

        assert response.status_code == 200
        messages = response.json()
        returned_ids = [message["id"] for message in messages]
        assert all(message_id in returned_ids for message_id in message_ids)
        assert returned_ids.index(message_ids[1]) < returned_ids.index(message_ids[0])
        for message in messages:
            assert set(message) == {
                "id", "student_id", "student_name", "message", "reply", "status", "created_at"
            }
            assert message["status"] == "open"
    finally:
        delete_messages(message_ids)


def test_faculty_sees_only_cohort_messages():
    faculty_headers = login("prof_sharma", "faculty123")
    cohort_student_id, outside_student_id = faculty_students()
    message_ids = [
        create_message(cohort_student_id, "Faculty inbox cohort test", datetime.utcnow()),
        create_message(outside_student_id, "Faculty inbox outside test", datetime.utcnow())
    ]
    try:
        response = client.get("/api/students/messages/inbox", headers=faculty_headers)

        assert response.status_code == 200
        returned_ids = {message["id"] for message in response.json()}
        assert message_ids[0] in returned_ids
        assert message_ids[1] not in returned_ids
    finally:
        delete_messages(message_ids)


def test_student_cannot_access_message_inbox():
    db = SessionLocal()
    try:
        student = db.query(Student).first()
        assert student is not None
        student_id = student.student_id
    finally:
        db.close()

    student_headers = login(student_id, "student123")
    response = client.get("/api/students/messages/inbox", headers=student_headers)

    assert response.status_code == 403


def test_reply_removes_message_from_inbox():
    faculty_headers = login("prof_sharma", "faculty123")
    cohort_student_id, _ = faculty_students()
    message_id = create_message(
        cohort_student_id,
        "Reply resolution inbox test",
        datetime.utcnow()
    )
    try:
        before_reply = client.get("/api/students/messages/inbox", headers=faculty_headers)
        assert before_reply.status_code == 200
        assert message_id in {message["id"] for message in before_reply.json()}

        reply_response = client.patch(
            f"/api/students/messages/{message_id}/reply",
            json={"reply": "Thanks for reaching out. Let's meet during office hours."},
            headers=faculty_headers
        )
        assert reply_response.status_code == 200

        after_reply = client.get("/api/students/messages/inbox", headers=faculty_headers)
        assert after_reply.status_code == 200
        assert message_id not in {message["id"] for message in after_reply.json()}
    finally:
        delete_messages([message_id])
