import os
import json
import re
import httpx
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from dotenv import load_dotenv

from app.database import get_db
from app.models import Student, StudentScore, UnifiedStudentMetrics, User
from app.auth import check_student_access, get_current_user
from app.routes_analytics import get_scoped_student_ids

load_dotenv()
router = APIRouter(prefix="/api", tags=["llm"])

LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()


class ExplainRequest(BaseModel):
    student_id: str
    focus: Optional[str] = None


class AskRequest(BaseModel):
    query: str
    student_id: Optional[str] = None


def generate_template_student_explanation(student: Student, score: StudentScore, m: UnifiedStudentMetrics) -> str:
    """Fallback template-based plain-English explanation."""
    clauses = []
    total = round(score.total_success_score) if score else 70
    clauses.append(f"{student.name} ({student.department}, Year {student.year}) has an overall Success Score of {total} out of 100.")

    if score and score.academic_risk_level in ["High", "Medium"]:
        clauses.append(f"Studies need support: CGPA is {m.cgpa:.1f} with {m.total_backlogs} course backlogs and attendance at {round(m.attendance_pct)}%.")
    else:
        clauses.append(f"Studies are on track with {m.cgpa:.1f} CGPA and {round(m.attendance_pct)}% attendance.")

    if score and score.placement_risk_level in ["High", "Medium"]:
        clauses.append(f"Job readiness needs support: coding practice is {round(m.coding_score)} out of 100 and {m.mock_interviews_completed} mock interviews completed.")
    else:
        clauses.append(f"Job readiness is solid with coding score {round(m.coding_score)} out of 100.")

    return " ".join(clauses)


def generate_student_explanation(student: Student, m: Optional[UnifiedStudentMetrics]) -> str:
    """Build supportive student-facing language using the student profile's focus areas."""
    focus_areas = []
    strengths = []
    if m:
        if m.attendance_pct < 80.0:
            focus_areas.append("Attendance Consistency: Boosting class participation to reach target 85%+")
        else:
            strengths.append(f"Strong attendance record ({m.attendance_pct:.1f}%)")

        if m.coding_score < 60.0:
            focus_areas.append("Coding Practice: Dedicated problem solving on core data structures")
        else:
            strengths.append(f"Solid coding assessment performance ({m.coding_score:.1f} pts)")

        if student.year >= 3 and m.mock_interviews_completed < 2:
            focus_areas.append("Placement Readiness: Completing your 2 recommended mock interview rounds")
        elif m.mock_interviews_completed >= 2:
            strengths.append("Completed recommended mock interview sessions")

        if m.assignments_submitted_pct < 85.0:
            focus_areas.append("Coursework Timeliness: Keeping all lab assignments and quizzes up to date")
        else:
            strengths.append(f"High coursework submission rate ({m.assignments_submitted_pct:.1f}%)")

    strengths = strengths or ["Consistent engagement with degree curriculum"]
    focus_areas = focus_areas or ["Keep maintaining your steady all-around performance!"]
    return f"Your strengths: {'; '.join(strengths)}. Focus areas: {'; '.join(focus_areas)}."


def get_analytics_aggregates(scoped_student_ids: Optional[list], db: Session) -> Dict[str, Any]:
    """Calculate analytics aggregates within the supplied student scope."""
    query = db.query(Student).outerjoin(
        StudentScore, Student.student_id == StudentScore.student_id
    ).outerjoin(
        UnifiedStudentMetrics, Student.student_id == UnifiedStudentMetrics.student_id
    )
    if scoped_student_ids is not None:
        query = query.filter(Student.student_id.in_(scoped_student_ids))

    at_risk_count = query.filter(or_(
        StudentScore.academic_risk_level.in_(["High", "Medium"]),
        StudentScore.placement_risk_level.in_(["High", "Medium"])
    )).count()
    attendance_below_75_count = query.filter(
        UnifiedStudentMetrics.attendance_pct < 75.0
    ).count()
    placement_ready_count = query.filter(StudentScore.placement_score >= 70.0).count()

    department_averages = query.with_entities(
        Student.department,
        func.avg(StudentScore.total_success_score)
    ).group_by(Student.department).all()

    return {
        "at_risk_count": at_risk_count,
        "attendance_below_75_count": attendance_below_75_count,
        "placement_ready_count": placement_ready_count,
        "average_success_score_by_department": {
            department: round(float(average), 1)
            for department, average in department_averages
            if average is not None
        }
    }


def generate_template_qa_response(query: str, aggregates: Dict[str, Any]) -> str:
    """Fallback keyword synthesis from the scoped analytics aggregates."""
    q_lower = query.lower()

    if "risk" in q_lower or "probation" in q_lower or "support" in q_lower or "attention" in q_lower:
        return f"{aggregates['at_risk_count']} students in the accessible cohort have elevated academic or placement risk."

    if "placement" in q_lower or "coding" in q_lower or "job" in q_lower:
        return f"{aggregates['placement_ready_count']} students in the accessible cohort are on track for job readiness."

    if "attendance" in q_lower:
        return f"{aggregates['attendance_below_75_count']} students in the accessible cohort have attendance below 75%."

    return (
        f"The accessible cohort has {aggregates['at_risk_count']} students with elevated academic or placement risk, "
        f"{aggregates['attendance_below_75_count']} with attendance below 75%, and "
        f"{aggregates['placement_ready_count']} on track for job readiness."
    )


def redact_student_identifiers(query: str, db: Session) -> str:
    """Remove known student names and IDs before including a question in an LLM prompt."""
    identifiers = db.query(Student.student_id, Student.name).all()
    redacted_query = query
    for identifier in sorted(
        {value for row in identifiers for value in row if value},
        key=len,
        reverse=True
    ):
        redacted_query = re.sub(
            rf"(?<![A-Za-z0-9]){re.escape(identifier)}(?![A-Za-z0-9])",
            "[redacted]",
            redacted_query,
            flags=re.IGNORECASE
        )
    return redacted_query


@router.post("/explain")
async def explain_student(
    payload: ExplainRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    POST /api/explain: Generates plain-English narrative explanation for a student's score and risk factors.
    Uses LLM_API_KEY if configured; silently falls back to template engine if missing or on failure.
    """
    check_student_access(payload.student_id, current_user, db)

    student = db.query(Student).filter(Student.student_id == payload.student_id.strip().upper()).first()
    if not student:
        return {"explanation": "Student profile not found.", "source": "fallback"}

    score = student.score
    m = student.unified_metrics

    if current_user.role == "STUDENT":
        return {
            "explanation": generate_student_explanation(student, m),
            "source": "template"
        }

    # Fallback default
    template_text = generate_template_student_explanation(student, score, m)

    if not LLM_API_KEY:
        return {"explanation": template_text, "source": "template"}

    # Attempt LLM call
    try:
        prompt = (
            f"Analyze this student's university profile and provide a concise 3-sentence institutional briefing:\n"
            f"Name: {student.name}, Dept: {student.department}, Year: {student.year}\n"
            f"Success Score: {score.total_success_score if score else 'N/A'}/100\n"
            f"CGPA: {m.cgpa}, Backlogs: {m.total_backlogs}, Attendance: {m.attendance_pct}%\n"
            f"Coding Score: {m.coding_score}, Aptitude: {m.aptitude_score}, Mock Interviews: {m.mock_interviews_completed}\n"
            f"Academic Risk: {score.academic_risk_level if score else 'N/A'}, Placement Risk: {score.placement_risk_level if score else 'N/A'}."
        )

        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
                headers={"x-goog-api-key": LLM_API_KEY},
                json={"contents": [{"parts": [{"text": prompt}]}]}
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return {"explanation": text, "source": "llm"}
    except Exception:
        pass

    return {"explanation": template_text, "source": "template"}


@router.post("/ask")
async def ask_analytics(
    payload: AskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    POST /api/ask: Analytical Q&A assistant for institutional inquiries.
    Uses LLM_API_KEY if configured; silently falls back to keyword synthesis if missing or on failure.
    """
    if current_user.role not in ["ADMIN", "FACULTY"]:
        raise HTTPException(status_code=403, detail="Only faculty and admins may use campus analytics")

    scoped_student_ids = get_scoped_student_ids(current_user, db)
    aggregates = get_analytics_aggregates(scoped_student_ids, db)
    template_answer = generate_template_qa_response(payload.query, aggregates)

    if not LLM_API_KEY:
        return {"answer": template_answer, "source": "keyword_synthesis"}

    try:
        safe_query = redact_student_identifiers(payload.query, db)
        prompt = (
            "You are Smart Campus Analytics AI. Answer using ONLY the aggregate JSON below. "
            "If the requested information is not present in the JSON, reply exactly: "
            "\"I don't have that data\". Do not invent or infer additional information.\n"
            f"Aggregate JSON:\n{json.dumps(aggregates, sort_keys=True)}\n"
            f"Question: {safe_query}"
        )

        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
                headers={"x-goog-api-key": LLM_API_KEY},
                json={"contents": [{"parts": [{"text": prompt}]}]}
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return {"answer": text, "source": "llm"}
    except Exception:
        pass

    return {"answer": template_answer, "source": "keyword_synthesis"}
