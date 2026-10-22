from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models import User, Student, InterventionAction, FacultyAssignment
from app.auth import get_current_user

router = APIRouter(prefix="/api/interventions", tags=["interventions"])


class ActionUpdate(BaseModel):
    status: Optional[str] = None  # pending, in_progress, done
    notes: Optional[str] = None


@router.get("")
def list_interventions(
    status_filter: Optional[str] = Query(None, alias="status"),
    student_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Weekly Action List sorted by priority = potential gain x urgency.
    Scoped by role:
    - ADMIN: all actions
    - FACULTY: only their assigned students
    - STUDENT: only their own actions (presented supportively as 'My Next Steps')
    """
    query = db.query(InterventionAction).join(Student, InterventionAction.student_id == Student.student_id)

    # Scoping
    if current_user.role == "FACULTY":
        query = query.filter(
            or_(
                InterventionAction.mentor_id == current_user.id,
                Student.mentor_id == current_user.id,
                Student.student_id.in_(
                    db.query(FacultyAssignment.student_id).filter(FacultyAssignment.faculty_id == current_user.id)
                )
            )
        )
    elif current_user.role == "STUDENT":
        user_sid = (current_user.student_id or "").strip().upper()
        query = query.filter(InterventionAction.student_id == user_sid)

    if student_id:
        query = query.filter(InterventionAction.student_id == student_id.strip().upper())

    if status_filter and status_filter != "all":
        query = query.filter(InterventionAction.status == status_filter)

    # Sort descending by priority (gain x urgency)
    actions = query.order_by(InterventionAction.priority.desc()).all()

    items = []
    for a in actions:
        st = a.student
        item = {
            "id": a.id,
            "student_id": a.student_id,
            "student_name": st.name if st else a.student_id,
            "department": st.department if st else "",
            "year": st.year if st else 0,
            "action_type": a.action_type,
            "description": a.description,
            "status": a.status,
            "notes": a.notes or "",
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None
        }

        # Do not expose priority calculation or urgency to students
        if current_user.role != "STUDENT":
            item["potential_gain"] = a.potential_gain
            item["urgency"] = a.urgency
            item["priority"] = a.priority

        items.append(item)

    return {
        "count": len(items),
        "interventions": items
    }


@router.patch("/{action_id}")
def update_intervention(
    action_id: int,
    payload: ActionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update intervention status (pending, in_progress, done) or notes.
    Persists to SQLite database!
    """
    action = db.query(InterventionAction).filter(InterventionAction.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Intervention action not found")

    # Access check: students can update their own next steps status; staff can update any scoped action
    if current_user.role == "STUDENT":
        if (current_user.student_id or "").upper() != action.student_id.upper():
            raise HTTPException(status_code=403, detail="Forbidden: You can only update your own action items")

    if payload.status:
        valid_statuses = ["pending", "in_progress", "done"]
        if payload.status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Status must be one of: {valid_statuses}")
        action.status = payload.status

    if payload.notes is not None:
        action.notes = payload.notes

    action.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(action)

    return {
        "status": "success",
        "id": action.id,
        "new_status": action.status,
        "notes": action.notes,
        "updated_at": action.updated_at.isoformat()
    }
