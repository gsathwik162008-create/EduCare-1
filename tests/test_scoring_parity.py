import json
import subprocess
import os
import pytest
from app.scoring import compute_indicator_scores, compute_success_score
from app.models import UnifiedStudentMetrics


def test_python_js_scoring_parity():
    """
    Validates that the JavaScript scoring implementation (static/js/scoring.js)
    produces identical results to Python (app/scoring.py) across diverse student profiles.
    """
    test_cases = [
        # (cgpa, backlogs, att, apt, code, mocks, assigns, logins, forum, events, tech, soft, fac_fb, peer_fb)
        (8.5, 0, 92.0, 75.0, 85.0, 2, 95.0, 160, 8, 4, 88.0, 82.0, 90.0, 85.0),
        (5.2, 2, 64.0, 42.0, 32.0, 0, 55.0, 40, 0, 0, 45.0, 50.0, 55.0, 60.0),
        (7.0, 1, 78.5, 60.0, 55.0, 1, 80.0, 100, 3, 2, 65.0, 70.0, 75.0, 72.0),
        (9.8, 0, 98.0, 95.0, 94.0, 3, 100.0, 220, 15, 6, 95.0, 90.0, 95.0, 92.0),
        (4.1, 4, 50.0, 30.0, 20.0, 0, 40.0, 25, 0, 0, 35.0, 40.0, 45.0, 50.0),
        (6.8, 0, 82.0, 80.0, 75.0, 2, 85.0, 110, 4, 3, 70.0, 75.0, 80.0, 78.0),
        (7.5, 0, 74.0, 50.0, 38.0, 0, 70.0, 80, 2, 1, 60.0, 65.0, 70.0, 68.0),
        (8.0, 1, 88.0, 70.0, 65.0, 1, 90.0, 140, 5, 2, 75.0, 80.0, 82.0, 80.0),
        (9.1, 0, 91.0, 88.0, 90.0, 2, 92.0, 180, 10, 5, 90.0, 85.0, 88.0, 86.0),
        (6.0, 3, 68.0, 45.0, 40.0, 0, 60.0, 50, 1, 0, 50.0, 55.0, 60.0, 58.0),
    ]

    weights = {
        "weight_academic": 35.0,
        "weight_attendance": 20.0,
        "weight_placement": 20.0,
        "weight_lms": 15.0,
        "weight_skills": 10.0
    }

    # Prepare inputs for Node.js evaluation
    js_inputs = []
    py_results = []

    test_years = [3] * len(test_cases) + [1, 2]
    cases_with_early_years = test_cases + [test_cases[0], test_cases[1]]

    for idx, (cgpa, bl, att, apt, code, mocks, assigns, logins, forum, events, tech, soft, fac_fb, peer_fb) in enumerate(cases_with_early_years):
        year = test_years[idx]
        m = UnifiedStudentMetrics(
            student_id=f"TEST_{idx}",
            cgpa=cgpa,
            total_backlogs=bl,
            attendance_pct=att,
            aptitude_score=apt,
            coding_score=code,
            mock_interviews_completed=mocks,
            assignments_submitted_pct=assigns,
            lms_login_count=logins,
            forum_posts_count=forum,
            event_participation_count=events,
            technical_skills_score=tech,
            soft_skills_score=soft,
            faculty_feedback_score=fac_fb,
            peer_feedback_score=peer_fb
        )

        py_sub = compute_indicator_scores(m, year=year)
        py_total = compute_success_score(
            py_sub,
            w_acad=weights["weight_academic"],
            w_att=weights["weight_attendance"],
            w_place=weights["weight_placement"],
            w_lms=weights["weight_lms"],
            w_skills=weights["weight_skills"]
        )

        py_results.append({
            "sub": py_sub,
            "total": py_total
        })

        js_inputs.append({
            "cgpa": cgpa,
            "total_backlogs": bl,
            "attendance_pct": att,
            "aptitude_score": apt,
            "coding_score": code,
            "mock_interviews_completed": mocks,
            "assignments_submitted_pct": assigns,
            "lms_login_count": logins,
            "forum_posts_count": forum,
            "event_participation_count": events,
            "technical_skills_score": tech,
            "soft_skills_score": soft,
            "faculty_feedback_score": fac_fb,
            "peer_feedback_score": peer_fb,
            "year": year
        })

    # Execute static/js/scoring.js via node with input data
    js_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "js", "scoring.js"))
    js_path_escaped = js_path.replace("\\", "/")

    node_script = f"""
    import {{ computeIndicatorScores, computeSuccessScore }} from 'file:///{js_path_escaped}';
    const inputs = {json.dumps(js_inputs)};
    const weights = {json.dumps(weights)};

    const results = inputs.map(input => {{
        const sub = computeIndicatorScores(input, input.year);
        const total = computeSuccessScore(sub, weights);
        return {{ sub, total }};
    }});

    console.log(JSON.stringify(results));
    """

    res = subprocess.run(
        ["node", "--input-type=module", "-e", node_script],
        capture_output=True,
        text=True,
        check=True
    )

    js_results = json.loads(res.stdout)

    assert len(js_results) == len(py_results)

    for idx, (py, js) in enumerate(zip(py_results, js_results)):
        # Check total score
        assert abs(py["total"] - js["total"]) <= 0.01, f"Case {idx} total mismatch: Py={py['total']}, JS={js['total']}"

        # Check all 5 sub-scores
        for k in ["academic_score", "attendance_score", "placement_score", "lms_score", "skills_feedback_score"]:
            diff = abs(py["sub"][k] - js["sub"][k])
            assert diff <= 0.01, f"Case {idx} key {k} mismatch: Py={py['sub'][k]}, JS={js['sub'][k]}"
    
    print(f"Verified perfect mathematical parity across {len(test_cases)} test cases!")
