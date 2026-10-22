from typing import List, Dict, Any
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from app.models import UnifiedStudentMetrics, Student


def assign_rule_segment(metrics: UnifiedStudentMetrics) -> str:
    """Assigns rule-based student segmentation group."""
    cgpa = float(metrics.cgpa or 0.0)
    att = float(metrics.attendance_pct or 0.0)
    code = float(metrics.coding_score or 0.0)
    assigns = float(metrics.assignments_submitted_pct or 0.0)
    mocks = int(metrics.mock_interviews_completed or 0)

    if cgpa >= 8.5 and code >= 75.0 and att >= 85.0:
        return "Stars"
    if cgpa >= 7.5 and (code < 45.0 or mocks == 0):
        return "High Academics / Low Placement Readiness"
    if cgpa < 6.0 and att >= 75.0:
        return "Silent Strugglers"
    if att < 70.0 and assigns < 65.0:
        return "Disengaging"

    return "Steady Performers"


def compute_kmeans_segments(metrics_list: List[UnifiedStudentMetrics]) -> Dict[str, str]:
    """
    Fits K-Means clustering (k=4) on standardized student indicators and returns
    mapping of {student_id: readable_cluster_name}.
    """
    if not metrics_list or len(metrics_list) < 4:
        return {m.student_id: "Standard Cohort" for m in metrics_list}

    records = []
    sids = []
    for m in metrics_list:
        sids.append(m.student_id)
        records.append([
            float(m.cgpa or 0.0) * 10.0,
            float(m.attendance_pct or 0.0),
            float(m.coding_score or 0.0),
            float(m.assignments_submitted_pct or 0.0),
            float(m.technical_skills_score or 0.0)
        ])

    X = np.array(records)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
    cluster_labels = kmeans.fit_predict(X_scaled)
    centroids = kmeans.cluster_centers_

    # Map cluster indices to human-readable descriptive profiles based on centroids
    # Features: [academic, attendance, coding, assignments, technical]
    profile_names = {}
    cluster_scores = []
    for i in range(4):
        c = centroids[i]
        overall = float(np.mean(c))
        acad = float(c[0])
        code = float(c[2])
        att = float(c[1])
        cluster_scores.append((i, overall, acad, code, att))

    # Rank clusters by overall score
    cluster_scores.sort(key=lambda x: x[1], reverse=True)
    profile_names[cluster_scores[0][0]] = "High Achievers & Campus Leaders"
    profile_names[cluster_scores[3][0]] = "At-Risk & Disengaged"

    # Distinguish intermediate clusters
    rem1, rem2 = cluster_scores[1], cluster_scores[2]
    if rem1[3] > rem2[3]:  # higher coding
        profile_names[rem1[0]] = "Placement-Ready Tech Specialists"
        profile_names[rem2[0]] = "Academic-Focused Core Students"
    else:
        profile_names[rem1[0]] = "Academic-Focused Core Students"
        profile_names[rem2[0]] = "Placement-Ready Tech Specialists"

    result = {}
    for sid, label_idx in zip(sids, cluster_labels):
        result[sid] = profile_names.get(label_idx, f"Segment {label_idx + 1}")

    return result
