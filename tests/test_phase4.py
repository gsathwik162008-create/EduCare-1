import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import Student, User, InterventionAction

client = TestClient(app)


def test_auth_and_login():
    # 1. Admin login
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200
    data = res.json()
    assert data["role"] == "ADMIN"
    assert "access_token" in data
    admin_token = data["access_token"]

    # 2. Invalid password
    bad_res = client.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert bad_res.status_code == 401

    # 3. Faculty login
    fac_res = client.post("/api/auth/login", json={"username": "prof_sharma", "password": "faculty123"})
    assert fac_res.status_code == 200
    assert fac_res.json()["role"] == "FACULTY"

    # 4. Student login
    db = SessionLocal()
    sample_student = db.query(Student).first()
    db.close()
    assert sample_student is not None

    stud_res = client.post("/api/auth/login", json={"username": sample_student.student_id, "password": "student123"})
    assert stud_res.status_code == 200
    assert stud_res.json()["role"] == "STUDENT"


def test_student_directory_role_scoping():
    # Login admin
    admin_token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Login faculty
    fac_token = client.post("/api/auth/login", json={"username": "prof_sharma", "password": "faculty123"}).json()["access_token"]
    fac_headers = {"Authorization": f"Bearer {fac_token}"}

    # Fetch 2 students from DB
    db = SessionLocal()
    fac_user = db.query(User).filter(User.username == "prof_sharma").first()
    assigned_student = db.query(Student).filter(Student.mentor_id == fac_user.id).first()
    other_student = db.query(Student).filter(Student.mentor_id != fac_user.id).first()
    db.close()

    # Login student
    stud_token = client.post("/api/auth/login", json={"username": assigned_student.student_id, "password": "student123"}).json()["access_token"]
    stud_headers = {"Authorization": f"Bearer {stud_token}"}

    # 1. Admin gets all students
    res_admin = client.get("/api/students?limit=200", headers=admin_headers)
    assert res_admin.status_code == 200
    assert res_admin.json()["total"] == 600

    # 2. Faculty gets only their assigned cohort (120 students)
    res_fac = client.get("/api/students?limit=200", headers=fac_headers)
    assert res_fac.status_code == 200
    assert res_fac.json()["total"] == 120

    # 3. Student attempting to list all students gets 403 Forbidden
    res_stud = client.get("/api/students", headers=stud_headers)
    assert res_stud.status_code == 403


def test_individual_student_profile_access():
    db = SessionLocal()
    fac1_user = db.query(User).filter(User.username == "prof_sharma").first()
    s_assigned = db.query(Student).filter(Student.mentor_id == fac1_user.id).first()
    s_other = db.query(Student).filter(Student.mentor_id != fac1_user.id).first()
    db.close()

    admin_token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    fac1_token = client.post("/api/auth/login", json={"username": "prof_sharma", "password": "faculty123"}).json()["access_token"]
    s_assigned_token = client.post("/api/auth/login", json={"username": s_assigned.student_id, "password": "student123"}).json()["access_token"]

    # 1. Faculty accessing assigned student -> 200 OK
    res1 = client.get(f"/api/students/{s_assigned.student_id}", headers={"Authorization": f"Bearer {fac1_token}"})
    assert res1.status_code == 200
    assert "academic_risk_level" in res1.json()

    # 2. Faculty accessing unassigned student -> 403 Forbidden
    res2 = client.get(f"/api/students/{s_other.student_id}", headers={"Authorization": f"Bearer {fac1_token}"})
    assert res2.status_code == 403

    # 3. Student accessing their own record -> 200 OK (supportive view, risk labels omitted)
    res3 = client.get(f"/api/students/{s_assigned.student_id}", headers={"Authorization": f"Bearer {s_assigned_token}"})
    assert res3.status_code == 200
    data3 = res3.json()
    assert "academic_risk_level" not in data3  # Must never expose risk labels to students!
    assert "focus_areas" in data3
    assert "strengths" in data3

    # 4. Student accessing ANOTHER student's record -> 403 Forbidden!
    res4 = client.get(f"/api/students/{s_other.student_id}", headers={"Authorization": f"Bearer {s_assigned_token}"})
    assert res4.status_code == 403


def test_intervention_status_persistence():
    admin_token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Fetch list
    list_res = client.get("/api/interventions", headers=headers)
    assert list_res.status_code == 200
    actions = list_res.json()["interventions"]
    assert len(actions) > 0

    first_action = actions[0]
    action_id = first_action["id"]

    # Update status to in_progress
    patch_res = client.patch(
        f"/api/interventions/{action_id}",
        json={"status": "in_progress", "notes": "Contacted student during office hours."},
        headers=headers
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["new_status"] == "in_progress"

    # Verify directly from DB that change persisted
    db = SessionLocal()
    db_action = db.query(InterventionAction).filter(InterventionAction.id == action_id).first()
    assert db_action.status == "in_progress"
    assert db_action.notes == "Contacted student during office hours."
    db.close()


def test_llm_fallback():
    admin_token = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    db = SessionLocal()
    sid = db.query(Student.student_id).first()[0]
    db.close()

    # /explain
    exp_res = client.post("/api/explain", json={"student_id": sid}, headers=headers)
    assert exp_res.status_code == 200
    assert "explanation" in exp_res.json()
    assert len(exp_res.json()["explanation"]) > 10

    # /ask
    ask_res = client.post("/api/ask", json={"query": "Which department has highest placement readiness?"}, headers=headers)
    assert ask_res.status_code == 200
    assert "answer" in ask_res.json()
    assert len(ask_res.json()["answer"]) > 10
