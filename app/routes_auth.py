from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    name: str
    student_id: str | None = None


@router.post("/login", response_model=LoginResponse)
def login(creds: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user with username and password; returns JWT access token."""
    username_clean = creds.username.strip()
    user = db.query(User).filter(User.username.ilike(username_clean)).first()

    if not user or not verify_password(creds.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    token = create_access_token({
        "sub": user.username,
        "role": user.role,
        "student_id": user.student_id
    })

    display_name = user.faculty_name if user.faculty_name else (user.student_id or user.username)

    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
        "name": display_name,
        "student_id": user.student_id
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Returns currently authenticated user profile."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "faculty_name": current_user.faculty_name,
        "student_id": current_user.student_id,
        "email": current_user.email
    }
