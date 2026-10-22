from typing import Dict, Any, Tuple, List
import json
import numpy as np
from sqlalchemy.orm import Session
from app.models import UnifiedStudentMetrics, StudentScore, Student, ScoreSettings


def compute_indicator_scores(
    metrics: UnifiedStudentMetrics,
    settings: ScoreSettings = None
) -> Dict[str, float]:
    """
    Computes normalized (0-100) sub-scores.
    NOTE: This formula is identical to the JavaScript implementation in static/js/scoring.js.
    """
    # 1. Academic Score (0-100)
    cgpa = max(0.0, min(10.0, float(metrics.cgpa or 0.0)))
    backlogs = max(0, int(metrics.total_backlogs or 0))
    # CGPA contributes up to 100, each backlog penalizes by 10 points
    academic_score = max(0.0, min(100.0, (cgpa * 10.0) - (backlogs * 10.0)))

    # 2. Attendance Score (0-100)
    att = max(0.0, min(100.0, float(metrics.attendance_pct or 0.0)))
    attendance_score = att

    # 3. Placement Readiness Score (0-100)
    apt = max(0.0, min(100.0, float(metrics.aptitude_score or 0.0)))
    code = max(0.0, min(100.0, float(metrics.coding_score or 0.0)))
    mocks = max(0, int(metrics.mock_interviews_completed or 0))
    mock_score = min(100.0, mocks * 50.0)  # 2 mock interviews = 100
    placement_score = round(0.35 * apt + 0.45 * code + 0.20 * mock_score, 2)

    # 4. LMS & Engagement Score (0-100)
    assign_pct = max(0.0, min(100.0, float(metrics.assignments_submitted_pct or 0.0)))
    logins = max(0, int(metrics.lms_login_count or 0))
    login_score = min(100.0, (logins / 150.0) * 100.0)
    forum_posts = max(0, int(metrics.forum_posts_count or 0))
    events = max(0, int(metrics.event_participation_count or 0))
    engagement_extra = min(100.0, (forum_posts * 10.0) + (events * 15.0))
    lms_score = round(0.50 * assign_pct + 0.30 * login_score + 0.20 * engagement_extra, 2)

    # 5. Skills & Feedback Score (0-100)
    tech = max(0.0, min(100.0, float(metrics.technical_skills_score or 0.0)))
    soft = max(0.0, min(100.0, float(metrics.soft_skills_score or 0.0)))
    fac_fb = max(0.0, min(100.0, float(metrics.faculty_feedback_score or 0.0)))
    peer_fb = max(0.0, min(100.0, float(metrics.peer_feedback_score or 0.0)))
    skills_score = round(0.35 * tech + 0.25 * soft + 0.20 * fac_fb + 0.20 * peer_fb, 2)

    return {
        "academic_score": round(academic_score, 2),
        "attendance_score": round(attendance_score, 2),
        "placement_score": round(placement_score, 2),
        "lms_score": round(lms_score, 2),
        "skills_feedback_score": round(skills_score, 2)
    }


def compute_success_score(
    sub_scores: Dict[str, float],
    w_acad: float = 35.0,
    w_att: float = 20.0,
    w_place: float = 20.0,
    w_lms: float = 15.0,
    w_skills: float = 10.0
) -> float:
    """
    Computes weighted success score (0-100).
    Formula identical to JavaScript implementation.
    """
    total_weight = w_acad + w_att + w_place + w_lms + w_skills
    if total_weight <= 0:
        total_weight = 100.0

    raw_sum = (
        sub_scores["academic_score"] * w_acad +
        sub_scores["attendance_score"] * w_att +
        sub_scores["placement_score"] * w_place +
        sub_scores["lms_score"] * w_lms +
        sub_scores["skills_feedback_score"] * w_skills
    )

    total_score = max(0.0, min(100.0, raw_sum / total_weight))
    return round(total_score, 2)


def generate_score_explanation(
    sub_scores: Dict[str, float],
    cohort_averages: Dict[str, float],
    weights: Dict[str, float]
) -> str:
    """
    Generates plain-English explanation based on indicator contributions vs cohort average.
    """
    drivers = []
    # Contribution = weight * (student_val - cohort_avg) / 100
    for key, label in [
        ("academic_score", "Academic Performance"),
        ("attendance_score", "Classroom Attendance"),
        ("placement_score", "Placement Readiness"),
        ("lms_score", "LMS & Coursework Engagement"),
        ("skills_feedback_score", "Technical & Soft Skills")
    ]:
        s_val = sub_scores.get(key, 50.0)
        c_val = cohort_averages.get(key, 50.0)
        w = weights.get(key, 20.0)
        diff = s_val - c_val
        contribution = (diff * w) / 100.0
        drivers.append((label, s_val, diff, contribution))

    # Sort by contribution
    drivers_sorted = sorted(drivers, key=lambda x: x[3], reverse=True)
    top_pos = drivers_sorted[0]
    top_neg = drivers_sorted[-1]

    parts = []
    if top_pos[2] >= 0:
        parts.append(f"Primary asset is {top_pos[0]} ({top_pos[1]:.1f}, {top_pos[2]:+.1f} pts vs cohort)")
    else:
        parts.append(f"Top factor is {top_pos[0]} ({top_pos[1]:.1f})")

    if top_neg[2] < -3.0:
        parts.append(f"Key drag factor is {top_neg[0]} ({top_neg[1]:.1f}, {top_neg[2]:.1f} pts below cohort average)")
    else:
        parts.append("Performs consistently near or above cohort baseline across remaining dimensions")

    return ". ".join(parts) + "."
