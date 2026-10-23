# Student Success Dashboard

A simple, clear dashboard for college faculty, administrators, and students.
Anyone can understand each screen in 5 seconds without data expertise.

---

## What This Platform Does

1. **Shows How Students Are Doing**: Calculates an overall **Success Score** out of 100 based on five areas (Studies 35%, Attendance 20%, Job readiness 20%, Online learning and activities 15%, Skills and feedback 10%).
2. **Spots Who Needs Help Early**: Clear status tags show **Needs attention: Urgent**, **Needs attention: Soon**, or **Needs attention: Doing fine**.
3. **Helps Advisors Take Action**: Recommends support steps ranked by who to help first, showing how many points the score can improve by.
4. **Protects Student Privacy**: Students never see risk flags or ranks; they see their strengths, focus areas, and next steps to grow.

---

## Quick Demo Credentials

Log in with any of these three demo accounts:

- **Administrator**:
  - Username: `admin`
  - Password: `admin123`
  - *Access*: All 600 college students, system scoring weights, and data upload.
- **Teacher / Faculty Advisor**:
  - Username: `prof_sharma`
  - Password: `faculty123`
  - *Access*: Assigned cohort of 120 students and weekly action list.
- **Student**:
  - Username: `21CIV036` (or any student roll number)
  - Password: `student123`
  - *Access*: Private personal progress, goal planner, next steps, and mentor messaging.

---

## Running the Platform Locally

1. Copy `.env.example` to `.env`, then generate a secret key:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   Set the generated value as `SECRET_KEY` in `.env`.
2. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the web server:
   ```bash
   python -m uvicorn app.main:app --reload --port 8000
   ```
4. Open your browser:
   ```
   http://127.0.0.1:8000/
   ```

---

## Running the Self-Test

To verify that all features, role boundaries, scoring calculations, and API endpoints work properly, run:

```bash
python selftest.py
```
