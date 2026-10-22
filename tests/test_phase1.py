import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.database import Base
from app.models import User, Student, FacultyAssignment
from app.auth import hash_password, verify_password, create_access_token, decode_access_token, check_student_access

# Setup in-memory SQLite DB for testing
TEST_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=TEST_ENGINE)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=TEST_ENGINE)


def test_password_hashing():
    pw = "SecretPass123"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPass", hashed) is False


def test_jwt_token():
    payload = {"sub": "faculty1", "role": "FACULTY"}
    token = create_access_token(payload)
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "faculty1"
    assert decoded["role"] == "FACULTY"


def test_role_enforcement_and_access(db_session):
    # Setup test users and students
    admin = User(username="admin", hashed_password=hash_password("admin123"), role="ADMIN")
    faculty1 = User(username="fac1", hashed_password=hash_password("fac123"), role="FACULTY", faculty_name="Prof. Sharma")
    faculty2 = User(username="fac2", hashed_password=hash_password("fac123"), role="FACULTY", faculty_name="Dr. Rao")
    student1_user = User(username="22CSE001", hashed_password=hash_password("stud123"), role="STUDENT", student_id="22CSE001")
    student2_user = User(username="22CSE002", hashed_password=hash_password("stud123"), role="STUDENT", student_id="22CSE002")

    db_session.add_all([admin, faculty1, faculty2, student1_user, student2_user])
    db_session.commit()

    stud1 = Student(student_id="22CSE001", name="Aarav Patel", department="CSE", year=3, semester=5, mentor_id=faculty1.id)
    stud2 = Student(student_id="22CSE002", name="Bhavya Reddy", department="CSE", year=3, semester=5, mentor_id=faculty2.id)
    db_session.add_all([stud1, stud2])
    db_session.commit()

    assignment1 = FacultyAssignment(faculty_id=faculty1.id, student_id="22CSE001")
    assignment2 = FacultyAssignment(faculty_id=faculty2.id, student_id="22CSE002")
    db_session.add_all([assignment1, assignment2])
    db_session.commit()

    # 1. Admin accesses any student -> True
    assert check_student_access("22CSE001", admin, db_session) is True
    assert check_student_access("22CSE002", admin, db_session) is True

    # 2. Faculty1 accesses assigned student -> True
    assert check_student_access("22CSE001", faculty1, db_session) is True

    # 3. Faculty1 accesses unassigned student -> 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        check_student_access("22CSE002", faculty1, db_session)
    assert exc_info.value.status_code == 403

    # 4. Student1 accesses own record -> True
    assert check_student_access("22CSE001", student1_user, db_session) is True

    # 5. Student1 accesses student2 record -> 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        check_student_access("22CSE002", student1_user, db_session)
    assert exc_info.value.status_code == 403
