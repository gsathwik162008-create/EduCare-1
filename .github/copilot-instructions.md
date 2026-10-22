# EduCare project rules
- Backend: FastAPI + SQLAlchemy + SQLite in /app. Frontend: vanilla JS in /static/js.
- Roles: ADMIN, FACULTY, STUDENT. Use require_role() and check_student_access() from app/auth.py for ALL access control.
- Students must NEVER see risk levels, risk reasons, priority, segments, or other students' data.
- Scoring formula in app/scoring.py must stay identical to static/js/scoring.js (tests/test_scoring_parity.py).
- Make minimal changes. Do not refactor unrelated code. Do not rename existing API routes.
- After every change, add/update pytest tests in /tests and make sure `python -m pytest -q tests` and `python selftest.py` pass.