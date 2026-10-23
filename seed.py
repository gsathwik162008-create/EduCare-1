import os
import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.database import engine, Base, SessionLocal
from app.models import User, Student, FacultyAssignment, InterventionAction, ScoreSettings, StudentScore
from app.auth import hash_password
from app.ingestion import ingest_seven_sources
from app.analytics_pipeline import run_full_analytics_pipeline

# Fix seeds for reproducibility
np.random.seed(42)
random.seed(42)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
    "Shaurya", "Atharv", "Dhruv", "Kabir", "Rohan", "Ananya", "Diya", "Isha", "Saanvi", "Aadhya",
    "Pari", "Ananya", "Navya", "Sneha", "Kavya", "Tanvi", "Meera", "Pooja", "Nisha", "Riya",
    "Pranav", "Rahul", "Nikhil", "Manish", "Gautam", "Suresh", "Karan", "Akash", "Vikram", "Deepak"
]

LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Reddy", "Rao", "Nair", "Iyer", "Gupta", "Singh", "Kumar",
    "Joshi", "Kulkarni", "Deshmukh", "Chowdhury", "Banerjee", "Mehta", "Bhat", "Pillai", "Menon", "Das"
]

DEPARTMENTS = ["CSE", "ECE", "EEE", "Mech", "Civil"]
MESSY_DEPTS = {
    "CSE": ["CSE", "C.S.E", "CS", "Computer Science", "Comp Sci"],
    "ECE": ["ECE", "E.C.E", "Electronics", "Electronics & Comm"],
    "EEE": ["EEE", "E.E.E", "Electrical", "Electrical & Electronics"],
    "Mech": ["Mech", "Mechanical", "Mech Engg"],
    "Civil": ["Civil", "Civil Engg", "C.E."]
}


def generate_raw_csv_datasets(num_students: int = 600) -> dict[str, pd.DataFrame]:
    """Generate realistic synthetic datasets with deliberate data quality issues."""
    records = []
    
    # Generate base student demographic & academic metrics
    for i in range(1, num_students + 1):
        dept = np.random.choice(DEPARTMENTS, p=[0.35, 0.25, 0.15, 0.15, 0.10])
        year = np.random.choice([1, 2, 3, 4], p=[0.25, 0.25, 0.25, 0.25])
        semester = (year - 1) * 2 + np.random.choice([1, 2])
        
        # Roll number format: e.g., 22CSE014 (year batch + dept + 3-digit serial)
        batch_year = 25 - year  # 2024=1st yr (24), 2023=2nd (23), 2022=3rd (22), 2021=4th (21)
        serial = f"{i:03d}"
        clean_sid = f"{batch_year}{dept.upper()[:3]}{serial}"
        
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        
        # Correlated indicators:
        # latent_ability: -2 to +2
        latent_ability = np.random.normal(0, 1)
        
        # CGPA roughly 4.5 to 9.8
        base_cgpa = min(max(7.2 + 1.2 * latent_ability + np.random.normal(0, 0.4), 4.2), 9.9)
        backlogs = 0
        if base_cgpa < 6.0:
            backlogs = np.random.choice([1, 2, 3, 4], p=[0.4, 0.3, 0.2, 0.1])
        elif base_cgpa < 7.0:
            backlogs = np.random.choice([0, 1], p=[0.8, 0.2])
            
        # Attendance: correlated with CGPA
        att_pct = min(max(78.0 + 8.0 * latent_ability + np.random.normal(0, 5.0), 45.0), 99.0)
        
        # LMS engagement
        lms_logins = int(min(max(100 + 40 * latent_ability + np.random.normal(0, 20), 10), 300))
        lms_hours = round(min(max(40 + 20 * latent_ability + np.random.normal(0, 10), 5), 180), 1)
        assign_pct = min(max(82 + 10 * latent_ability + np.random.normal(0, 8), 30), 100)
        forum_posts = max(int(np.random.poisson(3 + max(0, latent_ability * 2))), 0)
        
        # Engagement
        events = max(int(np.random.poisson(2 + max(0, latent_ability))), 0)
        library = max(int(np.random.poisson(8 + max(0, latent_ability * 3))), 0)
        
        # Placement
        coding_score = round(min(max(55 + 22 * latent_ability + np.random.normal(0, 10), 15), 98), 1)
        aptitude_score = round(min(max(58 + 20 * latent_ability + np.random.normal(0, 8), 20), 96), 1)
        mock_interviews = 0
        if year >= 3:
            mock_interviews = int(min(max(int(1.5 + latent_ability + np.random.normal(0, 0.8)), 0), 4))
            
        # Skills
        tech_score = round(min(max(58 + 20 * latent_ability + np.random.normal(0, 10), 20), 98), 1)
        soft_score = round(min(max(65 + 15 * latent_ability + np.random.normal(0, 10), 25), 95), 1)
        
        # Feedback
        fac_feedback = round(min(max(70 + 15 * latent_ability + np.random.normal(0, 8), 35), 98), 1)
        peer_feedback = round(min(max(72 + 12 * latent_ability + np.random.normal(0, 8), 40), 98), 1)
        
        records.append({
            "student_id": clean_sid,
            "name": name,
            "department": dept,
            "year": year,
            "semester": semester,
            "cgpa": round(base_cgpa, 2),
            "backlogs": backlogs,
            "attendance_pct": round(att_pct, 1),
            "lms_login_count": lms_logins,
            "lms_time_spent_hrs": lms_hours,
            "assignments_submitted_pct": round(assign_pct, 1),
            "forum_posts_count": forum_posts,
            "event_participation_count": events,
            "library_visits": library,
            "aptitude_score": aptitude_score,
            "coding_score": coding_score,
            "mock_interviews_completed": mock_interviews,
            "technical_skills_score": tech_score,
            "soft_skills_score": soft_score,
            "faculty_feedback_score": fac_feedback,
            "peer_feedback_score": peer_feedback
        })

    df_base = pd.DataFrame(records)

    # Now create the 7 source dataframes with DELIBERATE MESS:
    # 1. Messy Academic CSV
    df_acad = df_base[["student_id", "name", "department", "year", "semester", "cgpa", "backlogs"]].copy()
    
    # Injected Mess 1: Inconsistent department spellings
    for idx in range(0, len(df_acad), 12):
        d = df_acad.loc[idx, "department"]
        df_acad.loc[idx, "department"] = random.choice(MESSY_DEPTS[d])
        
    # Injected Mess 2: CGPA entered on 100-point scale (e.g. 84.5 instead of 8.45)
    for idx in [5, 23, 77, 142]:
        if idx < len(df_acad):
            df_acad.loc[idx, "cgpa"] = round(df_acad.loc[idx, "cgpa"] * 10, 1)

    # Injected Mess 3: Missing values in CGPA and backlogs
    for idx in [12, 45, 98, 156]:
        if idx < len(df_acad):
            df_acad.loc[idx, "cgpa"] = np.nan
    for idx in [18, 62]:
        if idx < len(df_acad):
            df_acad.loc[idx, "backlogs"] = np.nan

    # Injected Mess 4: Untrimmed / lowercase student_id
    for idx in [3, 17, 33]:
        if idx < len(df_acad):
            orig = df_acad.loc[idx, "student_id"]
            df_acad.loc[idx, "student_id"] = f"  {orig.lower()}  "

    # Injected Mess 5: Duplicate rows
    dup_rows = df_acad.iloc[[10, 25, 50]].copy()
    df_acad = pd.concat([df_acad, dup_rows], ignore_index=True)

    # 2. Messy Attendance CSV
    df_att = df_base[["student_id", "attendance_pct"]].copy()
    df_att["lab_attendance_pct"] = np.clip(df_att["attendance_pct"] + np.random.uniform(-5, 5, len(df_att)), 40, 100).round(1)
    df_att["lecture_attendance_pct"] = np.clip(df_att["attendance_pct"] + np.random.uniform(-5, 5, len(df_att)), 40, 100).round(1)
    # Mess: attendance > 100% or missing
    df_att.loc[14, "attendance_pct"] = 108.5
    df_att.loc[28, "attendance_pct"] = -5.0
    df_att.loc[42, "attendance_pct"] = np.nan
    # Duplicate
    df_att = pd.concat([df_att, df_att.iloc[[14, 28]]], ignore_index=True)

    # 3. Messy LMS CSV
    df_lms = df_base[["student_id", "lms_login_count", "lms_time_spent_hrs", "assignments_submitted_pct", "forum_posts_count"]].copy()
    df_lms.loc[8, "lms_login_count"] = np.nan
    df_lms.loc[19, "assignments_submitted_pct"] = 115.0  # clipped
    df_lms.loc[31, "lms_time_spent_hrs"] = -10.0

    # 4. Messy Engagement CSV
    df_eng = df_base[["student_id", "event_participation_count", "library_visits"]].copy()
    df_eng["hackathons_attended"] = np.random.poisson(0.5, len(df_eng))
    df_eng.loc[7, "library_visits"] = np.nan

    # 5. Messy Placement CSV
    df_place = df_base[["student_id", "aptitude_score", "coding_score", "mock_interviews_completed"]].copy()
    df_place["resume_score"] = np.clip(df_place["aptitude_score"] + np.random.uniform(-10, 10, len(df_place)), 30, 95).round(1)
    df_place.loc[15, "coding_score"] = 120.0  # clipped
    df_place.loc[22, "aptitude_score"] = np.nan

    # 6. Messy Skills CSV
    df_skills = df_base[["student_id", "technical_skills_score", "soft_skills_score"]].copy()
    df_skills["certifications_count"] = np.random.choice([0, 1, 2, 3], p=[0.4, 0.3, 0.2, 0.1], size=len(df_skills))
    df_skills.loc[35, "technical_skills_score"] = np.nan

    # 7. Messy Feedback CSV
    df_fb = df_base[["student_id", "faculty_feedback_score", "peer_feedback_score"]].copy()
    df_fb.loc[55, "faculty_feedback_score"] = np.nan

    # Save to CSV files in data/
    df_acad.to_csv(os.path.join(DATA_DIR, "academic.csv"), index=False)
    df_att.to_csv(os.path.join(DATA_DIR, "attendance.csv"), index=False)
    df_lms.to_csv(os.path.join(DATA_DIR, "lms.csv"), index=False)
    df_eng.to_csv(os.path.join(DATA_DIR, "engagement.csv"), index=False)
    df_place.to_csv(os.path.join(DATA_DIR, "placement.csv"), index=False)
    df_skills.to_csv(os.path.join(DATA_DIR, "skills.csv"), index=False)
    df_fb.to_csv(os.path.join(DATA_DIR, "feedback.csv"), index=False)

    return {
        "academic": df_acad,
        "attendance": df_att,
        "lms": df_lms,
        "engagement": df_eng,
        "placement": df_place,
        "skills": df_skills,
        "feedback": df_fb
    }


def seed_database():
    """Wipe or initialize database, generate datasets, ingest, and create users."""
    print("=" * 60)
    print("SMART CAMPUS ANALYTICS - SYSTEM SEED & INITIALIZATION")
    print("=" * 60)
    
    # Re-create tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    
    try:
        # 1. Initialize default score settings
        default_settings = ScoreSettings(
            key="default",
            weight_academic=35.0,
            weight_attendance=20.0,
            weight_placement=20.0,
            weight_lms=15.0,
            weight_skills=10.0,
            threshold_academic_cgpa=6.0,
            threshold_attendance_pct=75.0,
            threshold_coding_score=40.0
        )
        db.add(default_settings)
        db.commit()

        # 2. Generate raw CSVs with deliberate mess
        print("\n[1/4] Generating synthetic raw datasets with injected anomalies...")
        datasets = generate_raw_csv_datasets(num_students=600)
        print("  - Saved 7 raw CSV files to data/ directory.")

        # 3. Ingest through standard ingestion pipeline
        print("\n[2/4] Running data through ingestion and cleaning pipeline...")
        ingest_result = ingest_seven_sources(datasets, db)
        print(f"  - Successfully ingested: {ingest_result['students_count']} students.")
        print(f"  - Cleaned & logged anomalies: {ingest_result['cleaning_logs_count']} logged events.")

        # 4. Create Users (1 Admin, 5 Faculty, 600 Students)
        print("\n[3/5] Creating system users and faculty assignments...", flush=True)
        
        # Admin
        admin = User(
            username="admin",
            hashed_password=hash_password("admin123"),
            role="ADMIN",
            faculty_name="Administrator",
            email="admin@campus.edu"
        )
        db.add(admin)
        db.flush()

        # 5 Faculty members
        faculty_roster = [
            ("prof_sharma", "Prof. Rajesh Sharma", "sharma@campus.edu"),
            ("dr_rao", "Dr. Sunita Rao", "rao@campus.edu"),
            ("prof_iyer", "Prof. Venkatesh Iyer", "iyer@campus.edu"),
            ("dr_reddy", "Dr. Ananya Reddy", "reddy@campus.edu"),
            ("prof_gupta", "Prof. Manoj Gupta", "gupta@campus.edu")
        ]
        
        faculty_users = []
        for uname, fname, femail in faculty_roster:
            fac = User(
                username=uname,
                hashed_password=hash_password("faculty123"),
                role="FACULTY",
                faculty_name=fname,
                email=femail
            )
            db.add(fac)
            db.flush()
            faculty_users.append(fac)

        # Distribute students evenly among the 5 faculty members
        students = db.query(Student).order_by(Student.student_id).all()
        student_users = []
        chunk_size = len(students) // len(faculty_users)
        student_pw_hash = hash_password("student123")

        for idx, s in enumerate(students):
            fac_idx = min(idx // chunk_size, len(faculty_users) - 1)
            assigned_fac = faculty_users[fac_idx]
            s.mentor_id = assigned_fac.id

            db.add(FacultyAssignment(
                faculty_id=assigned_fac.id,
                student_id=s.student_id
            ))

            # Student User
            s_user = User(
                username=s.student_id,
                hashed_password=student_pw_hash,
                role="STUDENT",
                student_id=s.student_id,
                email=s.email
            )
            student_users.append(s_user)

        db.bulk_save_objects(student_users)
        db.commit()

        print(f"  - Created 1 Admin, 5 Faculty, and {len(students)} Student users.", flush=True)

        # 5. Run initial analytics pipeline (Scores, Risks, Segments, ML Model, Interventions)
        print("\n[4/5] Executing analytics, scoring, risk classification, ML model & intervention ranking...", flush=True)
        pipeline_res = run_full_analytics_pipeline(db)
        print(f"  - Success! Computed scores for {pipeline_res['students_evaluated']} students.", flush=True)
        print(f"  - Trained Gradient Boosting ML model: 5-fold CV Accuracy = {pipeline_res['ml_model_metrics']['cv_accuracy']:.2%}, ROC-AUC = {pipeline_res['ml_model_metrics']['cv_roc_auc']:.2%}.", flush=True)
        print(f"  - Generated & ranked {pipeline_res['new_interventions_created']} intervention actions.", flush=True)

        random.seed(42)
        actions = db.query(InterventionAction).all()
        scores_map = {score.student_id: score for score in db.query(StudentScore).all()}
        now = datetime.now()
        for action in actions:
            score = scores_map.get(action.student_id)
            if score is None or random.random() >= 0.30:
                continue
            current_score = float(score.total_success_score)
            action.status = "done"
            action.score_at_creation = current_score - random.uniform(3.0, 8.0)
            action.score_at_completion = current_score
            action.completed_at = now - timedelta(seconds=random.uniform(0, 30 * 24 * 60 * 60))
        db.commit()

        print("\n[5/5] Seed complete! Demo credentials:", flush=True)
        print("-" * 50, flush=True)
        print("Role     | Username       | Password     | Details", flush=True)
        print("-" * 50, flush=True)
        print("ADMIN    | admin          | admin123     | System Administrator", flush=True)
        for fac in faculty_users:
            assigned_count = db.query(FacultyAssignment).filter(FacultyAssignment.faculty_id == fac.id).count()
            print(f"FACULTY  | {fac.username:<14} | faculty123   | {fac.faculty_name} ({assigned_count} students)", flush=True)
        print("-" * 50, flush=True)
        print("STUDENT (First 5 sample students):", flush=True)
        for s in students[:5]:
            print(f"STUDENT  | {s.student_id:<14} | student123   | {s.name} ({s.department}, Year {s.year})", flush=True)
        print("-" * 50, flush=True)

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
