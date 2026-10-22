import os
import httpx
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.database import get_db
from app.models import Student, StudentScore, UnifiedStudentMetrics, User
from app.auth import get_current_user

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


def generate_template_qa_response(query: str, db: Session) -> str:
    """Fallback keyword synthesis for analytical campus questions."""
    q_lower = query.lower()

    if "risk" in q_lower or "probation" in q_lower or "support" in q_lower or "attention" in q_lower:
        high_risk_count = db.query(StudentScore).filter(
            (StudentScore.academic_risk_level == "High") | (StudentScore.placement_risk_level == "High")
        ).count()
        return f"Across the college, {high_risk_count} students need urgent attention. Key reasons are attendance under 75% and needing mock interview practice."

    if "placement" in q_lower or "coding" in q_lower or "job" in q_lower:
        placed_count = db.query(StudentScore).filter(StudentScore.placement_score >= 70.0).count()
        return f"Currently, {placed_count} students are on track for job readiness with scores of 70 out of 100 or higher."

    if "attendance" in q_lower:
        sub_75 = db.query(UnifiedStudentMetrics).filter(UnifiedStudentMetrics.attendance_pct < 75.0).count()
        return f"There are {sub_75} students with attendance below the 75% minimum needed."

    return "College records show steady performance with active support in place for students needing attendance and interview help."


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
    student = db.query(Student).filter(Student.student_id == payload.student_id.strip().upper()).first()
    if not student:
        return {"explanation": "Student profile not found.", "source": "fallback"}

    score = student.score
    m = student.unified_metrics

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
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={LLM_API_KEY}",
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
    template_answer = generate_template_qa_response(payload.query, db)

    if not LLM_API_KEY:
        return {"answer": template_answer, "source": "keyword_synthesis"}

    try:
        prompt = (
            f"You are Smart Campus Analytics AI for college administrators. "
            f"Answer this query professionally in 2 sentences based on institutional data:\n"
            f"Question: {payload.query}"
        )

        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={LLM_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}]}
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return {"answer": text, "source": "llm"}
    except Exception:
        pass

    return {"answer": template_answer, "source": "keyword_synthesis"}
