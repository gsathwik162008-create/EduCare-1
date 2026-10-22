"""
Smart Campus Analytics - Comprehensive Self-Test Runner
Validates all phases, role scoping, scoring parity, API endpoints, and database health.
"""

import sys
import subprocess
import pytest
from fastapi.testclient import TestClient
from app.main import app

def run_pytest_suite():
    print("=" * 60)
    print("RUNNING PYTEST SUITE")
    print("=" * 60)
    ret = pytest.main(["-v", "tests"])
    if ret != 0:
        print("\n[FAIL] Pytest tests failed!")
        return False
    print("\n[PASS] All Pytest tests passed!")
    return True

def run_endpoint_health_checks():
    print("\n" + "=" * 60)
    print("RUNNING ENDPOINT HEALTH & ROLE SCOPING CHECKS")
    print("=" * 60)
    client = TestClient(app)

    # 1. Test Admin Login & Overview
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    admin_token = res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("[PASS] Admin authentication")

    # 2. Test Overview API
    overview_res = client.get("/api/analytics/overview", headers=admin_headers)
    assert overview_res.status_code == 200, f"Overview API failed: {overview_res.text}"
    ov = overview_res.json()
    assert ov["total_students"] == 600
    assert len(ov["department_heatmap"]) == 5
    print("[PASS] /api/analytics/overview (600 students, 5 departments)")

    # 3. Test Trends API
    trends_res = client.get("/api/analytics/trends", headers=admin_headers)
    assert trends_res.status_code == 200, f"Trends API failed: {trends_res.text}"
    tr = trends_res.json()
    assert len(tr["semester_trends"]) == 8
    print("[PASS] /api/analytics/trends (8 semesters)")

    # 4. Test Segments API
    seg_res = client.get("/api/analytics/segments", headers=admin_headers)
    assert seg_res.status_code == 200
    assert len(seg_res.json()["rule_segments"]) > 0
    print("[PASS] /api/analytics/segments")

    # 5. Test Insights API
    ins_res = client.get("/api/analytics/insights", headers=admin_headers)
    assert ins_res.status_code == 200
    assert len(ins_res.json()["auto_findings"]) > 0
    print("[PASS] /api/analytics/insights")

    # 6. Test Interventions API
    act_res = client.get("/api/interventions", headers=admin_headers)
    assert act_res.status_code == 200
    actions = act_res.json()["interventions"]
    assert len(actions) > 0
    print(f"[PASS] /api/interventions ({len(actions)} support actions)")

    # 7. Test Faculty Login and Student Scoping
    fac_res = client.post("/api/auth/login", json={"username": "prof_sharma", "password": "faculty123"})
    assert fac_res.status_code == 200
    fac_token = fac_res.json()["access_token"]
    fac_headers = {"Authorization": f"Bearer {fac_token}"}
    fac_studs = client.get("/api/students", headers=fac_headers).json()
    assert fac_studs["total"] == 120, f"Expected 120 assigned students for faculty, got {fac_studs['total']}"
    print("[PASS] Faculty role scoping (exactly 120 assigned students)")

    # 8. Test Student Login and Supportive Privacy
    sample_sid = fac_studs["students"][0]["student_id"]
    stud_login = client.post("/api/auth/login", json={"username": sample_sid, "password": "student123"})
    assert stud_login.status_code == 200
    stud_token = stud_login.json()["access_token"]
    stud_headers = {"Authorization": f"Bearer {stud_token}"}
    stud_profile = client.get(f"/api/students/{sample_sid}", headers=stud_headers).json()
    assert "academic_risk_level" not in stud_profile, "Student endpoint must NEVER expose risk labels!"
    assert "strengths" in stud_profile
    assert "focus_areas" in stud_profile
    print("[PASS] Student privacy enforcement (zero risk labels, supportive focus areas)")

    print("\n[PASS] All endpoint health checks passed!")
    return True

def main():
    py_ok = run_pytest_suite()
    api_ok = run_endpoint_health_checks()
    if py_ok and api_ok:
        print("\n" + "=" * 60)
        print("ALL SELF-TEST CHECKS PASSED PERFECTLY (0 ERRORS)")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n[FAIL] Self-test failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
