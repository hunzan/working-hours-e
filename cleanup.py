# cleanup.py
import os
from datetime import datetime, timedelta

from app import create_app
from models import db, Case, Teacher

DAYS_CLOSED_DELETE = int(os.environ.get("DAYS_CLOSED_DELETE", "60"))
DAYS_INACTIVE_DISABLE = int(os.environ.get("DAYS_INACTIVE_DISABLE", "90"))

def main():
    app = create_app()
    with app.app_context():
        now = datetime.utcnow()

        # 1) 刪除已結案超過 60 天的案件（整案刪，連 services/sessions 一起 cascade）
        cutoff_closed = now - timedelta(days=DAYS_CLOSED_DELETE)
        old_closed_cases = (
            Case.query
            .filter(Case.status == "closed")
            .filter(Case.closed_at.isnot(None))
            .filter(Case.closed_at <= cutoff_closed)
            .all()
        )
        for c in old_closed_cases:
            db.session.delete(c)

        # 2) 停用 90 天沒登入老師（且沒有 active 案件才停用，避免教到一半被停）
        cutoff_login = now - timedelta(days=DAYS_INACTIVE_DISABLE)
        stale_teachers = (
            Teacher.query
            .filter(Teacher.is_active == True)  # noqa
            .filter(Teacher.last_login_at.isnot(None))
            .filter(Teacher.last_login_at <= cutoff_login)
            .all()
        )
        for t in stale_teachers:
            active_cnt = Case.query.filter_by(teacher_id=t.id, status="active").count()
            if active_cnt == 0:
                t.is_active = False

        db.session.commit()
        print(f"✅ cleanup done: deleted_cases={len(old_closed_cases)}, disabled_teachers={len(stale_teachers)}")

if __name__ == "__main__":
    main()
