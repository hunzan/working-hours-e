from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()

class Teacher(db.Model):
    __tablename__ = "teachers"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    last_login_at = db.Column(db.DateTime, nullable=True)
    reset_count_year = db.Column(db.Integer, default=0, nullable=False)
    reset_count_year_tag = db.Column(db.Integer, default=datetime.utcnow().year, nullable=False)

    last_login_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    cases = db.relationship("Case", backref="teacher", cascade="all, delete-orphan")

class Case(db.Model):
    __tablename__ = "cases"
    id = db.Column(db.Integer, primary_key=True)

    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=False)

    student_name = db.Column(db.String(80), nullable=False, index=True)
    agency_name = db.Column(db.String(120), nullable=False, index=True)

    # 一案一碼：只存 hash，不存明碼
    query_code_hash = db.Column(db.String(255), nullable=False)
    query_code_enc = db.Column(db.String(500), nullable=True)  # 🔐 加密後的查詢碼（可解密
    query_code_hint = db.Column(db.String(10), nullable=True)  # 例如 **AB（尾2碼），可選

    status = db.Column(db.String(20), default="active", nullable=False)  # active/closed

    fiscal_year = db.Column(db.Integer, nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)

    services = db.relationship("CaseService", backref="case", cascade="all, delete-orphan")
    sessions = db.relationship("Session", backref="case", cascade="all, delete-orphan", order_by="Session.session_date.desc()")

class CaseService(db.Model):
    __tablename__ = "case_services"
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("cases.id"), nullable=False)

    # orientation / life
    service_type = db.Column(db.String(20), nullable=False)

    start_date = db.Column(db.Date, nullable=False, default=date.today)
    granted_hours = db.Column(db.Float, nullable=False, default=0.0)

class Session(db.Model):
    __tablename__ = "sessions"
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("cases.id"), nullable=False)

    session_date = db.Column(db.Date, nullable=False, default=date.today)

    # 一次上課可同時填兩項
    hours_orientation = db.Column(db.Float, nullable=False, default=0.0)
    hours_life = db.Column(db.Float, nullable=False, default=0.0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
