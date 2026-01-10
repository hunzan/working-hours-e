import os, io, csv, requests
from datetime import date, datetime

from flask import Flask, render_template, request, redirect, url_for, session as flask_session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash

from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from models import db, Teacher, Case, CaseService, Session
from utils import encrypt_code, decrypt_code, generate_query_code, today_after_jan10, service_label

mail = Mail()
serializer = None  # 之後在 create_app 內設定


def current_teacher():
    tid = flask_session.get("teacher_id")
    if not tid:
        return None
    return db.session.get(Teacher, tid)


def require_login():
    t = current_teacher()
    if not t or (hasattr(t, "is_active") and not t.is_active):
        flask_session.pop("teacher_id", None)
        flash("此帳號已停用（長期未登入）。請用忘記密碼/聯絡管理者恢復。", "warning")
        return redirect(url_for("teacher_login"))

    if not current_teacher():
        flash("請先登入用戶帳號。", "warning")
        return redirect(url_for("teacher_login"))
    return None

def send_reset_email(to_email: str, subject: str, body: str):
    api_key = os.environ.get("SENDGRID_API_KEY")
    mail_from = os.environ.get("MAIL_FROM")

    if not api_key or not mail_from:
        raise RuntimeError("Missing SENDGRID_API_KEY or MAIL_FROM")

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": mail_from},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

    r = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=10,
    )

    if r.status_code >= 400:
        raise RuntimeError(f"SendGrid error {r.status_code}: {r.text[:200]}")

def create_app():
    app = Flask(__name__)

    # =========================
    # 基本設定
    # =========================
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")
    db_url = os.environ.get("DATABASE_URL", "sqlite:///app.db")

    # SQLAlchemy 常見坑：有些平台給的是 postgres://，要改成 postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # =========================
    # ✉️ SMTP 寄信設定
    # =========================
    app.config["MAIL_SERVER"] = "smtp.gmail.com"
    app.config["MAIL_PORT"] = 587
    app.config["MAIL_USE_TLS"] = True
    app.config["MAIL_USERNAME"] = os.environ.get("SMTP_USER")
    app.config["MAIL_PASSWORD"] = os.environ.get("SMTP_PASS")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("SMTP_USER")

    # =========================
    # 套件初始化
    # =========================
    db.init_app(app)
    mail.init_app(app)

    global serializer
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

    # -------------------------
    # 首頁
    # -------------------------
    @app.route("/")
    def index():
        return render_template("index.html")

    # -------------------------
    # 自動年度清理：隔年 1/10 後刪除去年資料
    # -------------------------
    @app.before_request
    def cleanup_last_year_if_needed():
        # 🚨 預設關閉自動清理（避免 Railway deploy 時誤刪）
        if os.environ.get("ENABLE_AUTO_CLEANUP") != "1":
            return

        today = date.today()
        if not today_after_jan10(today):
            return

        last_year = today.year - 1
        old_cases = Case.query.filter_by(fiscal_year=last_year).all()
        if old_cases:
            for c in old_cases:
                db.session.delete(c)
            db.session.commit()
            print(f"🧹 AUTO CLEANUP: deleted {len(old_cases)} cases of year {last_year}")

    # =========================
    # ROUTES START
    # =========================
    # -------------------------
    # 用戶：登入/註冊（同頁）
    # -------------------------
    @app.route("/teacher/login", methods=["GET", "POST"])
    def teacher_login():
        if request.method == "POST":
            full_name = (request.form.get("full_name") or "").strip()
            password = request.form.get("password") or ""
            action = request.form.get("action")  # login / signup

            if not full_name or not password:
                flash("請輸入用戶全名與密碼。", "danger")
                return redirect(url_for("teacher_login"))

            t = Teacher.query.filter_by(full_name=full_name).first()

            # -------------------
            # signup
            # -------------------
            if action == "signup":
                email = (request.form.get("email") or "").strip().lower()
                if not email:
                    flash("註冊需要 Email（忘記密碼用）。", "danger")
                    return redirect(url_for("teacher_login"))

                if Teacher.query.filter_by(email=email).first():
                    flash("此 Email 已註冊，請改用登入或忘記密碼。", "warning")
                    return redirect(url_for("teacher_login"))

                if t:
                    flash("此用戶名稱已存在，請改用登入。", "warning")
                    return redirect(url_for("teacher_login"))

                t = Teacher(
                    full_name=full_name,
                    email=email,
                    password_hash=generate_password_hash(password),
                    last_login_at=datetime.utcnow(),
                )
                db.session.add(t)
                db.session.commit()

                flask_session["teacher_id"] = t.id
                flash("註冊成功，已登入。", "success")
                return redirect(url_for("dashboard"))

            # -------------------
            # login
            # -------------------
            if not t:
                flash("您尚未註冊，請先註冊再登入。", "warning")
                return redirect(url_for("teacher_login"))

            if not check_password_hash(t.password_hash, password):
                flash("登入失敗：密碼錯誤。", "danger")
                return redirect(url_for("teacher_login"))

            flask_session["teacher_id"] = t.id
            t.last_login_at = datetime.utcnow()
            db.session.commit()

            flash("登入成功。", "success")
            return redirect(url_for("dashboard"))

        return render_template("teacher_login.html")

    @app.get("/teacher/logout")
    def teacher_logout():
        flask_session.pop("teacher_id", None)
        flash("已登出。", "info")
        return redirect(url_for("index"))

    @app.route("/teacher/forgot", methods=["GET", "POST"])
    def teacher_forgot():
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            if not email:
                flash("請輸入 Email。", "danger")
                return redirect(url_for("teacher_forgot"))

            # ✅ 先查出老師（才能做年度計數）
            t = Teacher.query.filter_by(email=email).first()

            if t:
                now_year = datetime.utcnow().year

                # 年度標籤不一樣 → 代表跨年，歸零
                if t.reset_count_year_tag != now_year:
                    t.reset_count_year = 0
                    t.reset_count_year_tag = now_year

                # ✅ 每年限制（你之後可調整數字）
                LIMIT_PER_YEAR = 3
                if t.reset_count_year >= LIMIT_PER_YEAR:
                    # 仍然回同樣訊息（避免被探測），但不寄信
                    flash("若此 Email 已註冊，系統會寄出重設密碼連結。請查看收件匣/垃圾郵件。", "info")
                    return redirect(url_for("teacher_login"))

                # ✅ 計數 +1
                t.reset_count_year += 1
                db.session.commit()

                # 產生 token / link
                token = serializer.dumps({"tid": t.id}, salt="pw-reset")
                reset_link = url_for("teacher_reset", token=token, _external=True)

                subject = "工作時數 E 指通：重設密碼連結（30 分鐘有效）"
                body = (
                    "請點擊以下連結重設密碼（30 分鐘內有效）：\n"
                    f"{reset_link}\n\n"
                    "若你未申請重設，請忽略此信。"
                )

                try:
                    send_reset_email(email, subject, body)
                    print("✅ reset email sent ->", email)
                except Exception as e:
                    print("❌ reset email FAILED:", repr(e))
                    # 注意：這裡若顯示「寄信失敗」，其實會洩漏「這個 email 真的存在」
                    # 所以建議不要 flash danger，仍然回同樣訊息
                    # （真的要提示，可以只提示「系統忙碌」但不說寄信）
                    pass

            # ✅ 不管 t 存不存在，都回同樣訊息
            flash("若此 Email 已註冊，系統會寄出重設密碼連結。請查看收件匣/垃圾郵件。", "info")
            return redirect(url_for("teacher_login"))

        return render_template("teacher_forgot.html")

    @app.route("/teacher/reset/<token>", methods=["GET", "POST"])
    def teacher_reset(token):
        # 1) 驗證 token（30 分鐘）
        try:
            data = serializer.loads(token, salt="pw-reset", max_age=60 * 30)
            tid = data.get("tid")
        except SignatureExpired:
            flash("重設連結已過期，請重新申請一次。", "warning")
            return redirect(url_for("teacher_forgot"))
        except BadSignature:
            flash("重設連結無效，請重新申請一次。", "danger")
            return redirect(url_for("teacher_forgot"))

        t = db.session.get(Teacher, tid)
        if not t:
            flash("帳號不存在或已被刪除。", "danger")
            return redirect(url_for("teacher_forgot"))

        # 2) 設新密碼
        if request.method == "POST":
            pw1 = request.form.get("password") or ""
            pw2 = request.form.get("password2") or ""

            if len(pw1) < 8:
                flash("密碼至少 8 碼。", "warning")
                return redirect(url_for("teacher_reset", token=token))

            if pw1 != pw2:
                flash("兩次輸入的密碼不一致。", "warning")
                return redirect(url_for("teacher_reset", token=token))

            t.password_hash = generate_password_hash(pw1)
            db.session.commit()
            flash("密碼已更新，請用新密碼登入。", "success")
            return redirect(url_for("teacher_login"))

        return render_template("teacher_reset.html")

    # -------------------------
    # 用戶：儀表板（進行中 / 已結束）
    # -------------------------
    @app.get("/teacher/dashboard")
    def dashboard():
        guard = require_login()
        if guard:
            return guard
        t = current_teacher()

        q = Case.query.filter_by(teacher_id=t.id).order_by(Case.created_at.desc())
        active_cases = q.filter_by(status="active").all()
        closed_cases = q.filter_by(status="closed").all()

        return render_template(
            "dashboard.html",
            teacher=t,
            active_cases=active_cases,
            closed_cases=closed_cases,
            service_label=service_label,
        )

    # -------------------------
    # 用戶：新增案件（服務對象＋單位＋年度＋項目）
    # 一案一碼：定向/生活不分碼
    # -------------------------
    @app.route("/teacher/cases/new", methods=["GET", "POST"])
    def case_new():
        guard = require_login()
        if guard:
            return guard
        t = current_teacher()

        if request.method == "POST":
            student_name = (request.form.get("student_name") or "").strip()
            agency_name = (request.form.get("agency_name") or "").strip()
            fiscal_year = int(request.form.get("fiscal_year") or date.today().year)

            choose_orientation = request.form.get("choose_orientation") == "on"
            choose_life = request.form.get("choose_life") == "on"

            if not student_name or not agency_name:
                flash("請輸入服務對象姓名與派案單位。", "danger")
                return redirect(url_for("case_new"))

            if not (choose_orientation or choose_life):
                flash("請至少勾選一個工作項目（定向或生活）。", "danger")
                return redirect(url_for("case_new"))

            # 產生查詢碼（只顯示一次）
            code_plain = generate_query_code(8)
            code_hash = generate_password_hash(code_plain)
            code_enc = encrypt_code(code_plain)
            hint = f"**{code_plain[-2:]}"  # 尾2碼提示（可選）

            c = Case(
                teacher_id=t.id,
                student_name=student_name,
                agency_name=agency_name,
                query_code_hash=code_hash,
                query_code_enc=code_enc,
                query_code_hint=hint,
                status="active",
                fiscal_year=fiscal_year,
            )
            db.session.add(c)
            db.session.flush()  # 取得 c.id

            def parse_float(name: str):
                try:
                    return float(request.form.get(name) or 0)
                except:
                    return 0.0

            if choose_orientation:
                start_date = request.form.get("start_orientation") or str(date.today())
                granted = parse_float("granted_orientation")
                db.session.add(CaseService(
                    case_id=c.id,
                    service_type="orientation",
                    start_date=date.fromisoformat(start_date),
                    granted_hours=granted
                ))

            if choose_life:
                start_date = request.form.get("start_life") or str(date.today())
                granted = parse_float("granted_life")
                db.session.add(CaseService(
                    case_id=c.id,
                    service_type="life",
                    start_date=date.fromisoformat(start_date),
                    granted_hours=granted
                ))

            db.session.commit()

            flask_session["one_time_code"] = code_plain  # 一次性
            return redirect(url_for("case_detail", case_id=c.id))

        return render_template("case_new.html", this_year=date.today().year)

    # -------------------------
    # 用戶：案件詳情（新增上課、手動結案、重置查詢碼）
    # -------------------------
    @app.route("/teacher/cases/<int:case_id>", methods=["GET", "POST"])
    def case_detail(case_id):
        guard = require_login()
        if guard:
            return guard
        t = current_teacher()

        c = Case.query.filter_by(id=case_id, teacher_id=t.id).first_or_404()

        one_time_code = None

        # 取服務項目
        services = {s.service_type: s for s in c.services}

        # 計算已用/剩餘
        used_o = sum(s.hours_orientation for s in c.sessions)
        used_l = sum(s.hours_life for s in c.sessions)

        granted_o = services.get("orientation").granted_hours if "orientation" in services else 0.0
        granted_l = services.get("life").granted_hours if "life" in services else 0.0

        remaining_o = granted_o - used_o
        remaining_l = granted_l - used_l

        today = date.today().isoformat()

        if request.method == "POST":
            action = request.form.get("action")

            if action == "add_service":
                service_type = request.form.get("service_type")  # orientation / life
                if service_type not in ("orientation", "life"):
                    flash("項目不正確。", "danger")
                    return redirect(url_for("case_detail", case_id=case_id))

                if service_type in services:
                    flash("此項目已存在，無需新增。", "warning")
                    return redirect(url_for("case_detail", case_id=case_id))

                # 分別讀取欄位（避免表單撞名）
                if service_type == "orientation":
                    start_date = request.form.get("start_orientation") or str(date.today())
                    raw = request.form.get("granted_orientation")
                else:
                    start_date = request.form.get("start_life") or str(date.today())
                    raw = request.form.get("granted_life")

                try:
                    granted = float(raw or 0)
                except:
                    granted = 0.0

                if granted <= 0:
                    flash("核給時數需大於 0。", "danger")
                    return redirect(url_for("case_detail", case_id=case_id))

                db.session.add(CaseService(
                    case_id=c.id,
                    service_type=service_type,
                    start_date=date.fromisoformat(start_date),
                    granted_hours=granted
                ))
                db.session.commit()
                flash(f"已新增項目：{service_label(service_type)}（核給 {granted} 小時）。", "success")
                return redirect(url_for("case_detail", case_id=case_id))

            if action == "remove_service":
                service_type = request.form.get("service_type")
                if service_type not in services:
                    flash("此項目不存在。", "danger")
                    return redirect(url_for("case_detail", case_id=case_id))

                # 若已用過時數，不允許刪除（避免對帳亂掉）
                used_hours = 0.0
                if service_type == "orientation":
                    used_hours = sum(s.hours_orientation for s in c.sessions)
                else:
                    used_hours = sum(s.hours_life for s in c.sessions)

                if used_hours > 0:
                    flash("此項目已有上課時數紀錄，不能刪除。若真的要刪，請先將相關上課時數改為 0 或刪除該筆紀錄。",
                          "warning")
                    return redirect(url_for("case_detail", case_id=case_id))

                db.session.delete(services[service_type])
                db.session.commit()
                flash(f"已刪除項目：{service_label(service_type)}。", "info")
                return redirect(url_for("case_detail", case_id=case_id))

            if action == "update_granted":
                service_type = request.form.get("service_type")
                if service_type not in services:
                    flash("找不到該工作項目，無法修改。", "danger")
                    return redirect(url_for("case_detail", case_id=case_id))

                raw = request.form.get("new_granted_hours")
                try:
                    new_granted = float(raw)
                except:
                    flash("核給時數格式錯誤。", "danger")
                    return redirect(url_for("case_detail", case_id=case_id))

                if new_granted < 0:
                    flash("核給時數不可為負數。", "danger")
                    return redirect(url_for("case_detail", case_id=case_id))

                # 已用時數（避免核給改到比已用還小，造成對帳混亂）
                used_hours = 0.0
                if service_type == "orientation":
                    used_hours = sum(s.hours_orientation for s in c.sessions)
                else:
                    used_hours = sum(s.hours_life for s in c.sessions)

                if new_granted < used_hours:
                    flash(f"核給時數不可小於已用時數（已用 {used_hours}）。若要退回，請先確認是否要刪/改上課紀錄。",
                          "warning")
                    return redirect(url_for("case_detail", case_id=case_id))

                services[service_type].granted_hours = new_granted
                db.session.commit()
                flash(f"已更新 {service_label(service_type)} 核給時數為 {new_granted}。", "success")
                return redirect(url_for("case_detail", case_id=case_id))

            if action == "add_session":
                session_date = request.form.get("session_date") or str(date.today())
                try:
                    ho = float(request.form.get("hours_orientation") or 0)
                except:
                    ho = 0.0
                try:
                    hl = float(request.form.get("hours_life") or 0)
                except:
                    hl = 0.0

                # 沒有該項目就強制 0
                if "orientation" not in services:
                    ho = 0.0
                if "life" not in services:
                    hl = 0.0

                if ho < 0 or hl < 0 or (ho == 0 and hl == 0):
                    flash("請輸入有效時數（至少一項 > 0）。", "danger")
                    return redirect(url_for("case_detail", case_id=case_id))

                db.session.add(Session(
                    case_id=c.id,
                    session_date=date.fromisoformat(session_date),
                    hours_orientation=ho,
                    hours_life=hl
                ))
                db.session.commit()
                flash("已新增上課紀錄。", "success")
                return redirect(url_for("case_detail", case_id=case_id))

            if action == "toggle_close":
                if c.status == "active":
                    c.status = "closed"
                    c.closed_at = datetime.utcnow()
                    flash("已手動結案（移至已結束）。", "info")
                else:
                    c.status = "active"
                    c.closed_at = None
                    flash("已恢復為進行中。", "info")
                db.session.commit()
                return redirect(url_for("case_detail", case_id=case_id))

            if action == "reset_code":
                new_code = generate_query_code(8)
                c.query_code_hash = generate_password_hash(new_code)
                c.query_code_enc = encrypt_code(new_code)
                c.query_code_hint = f"**{new_code[-2:]}"
                db.session.commit()
                flask_session["one_time_code"] = new_code  # 一次性
                return redirect(url_for("case_detail", case_id=case_id))

            if action == "delete_case":
                db.session.delete(c)
                db.session.commit()
                flash("案件已刪除。", "info")
                return redirect(url_for("dashboard"))

            if action == "reveal_code":
                password_confirm = request.form.get("password_confirm") or ""
                if not check_password_hash(t.password_hash, password_confirm):
                    flash("密碼錯誤，無法顯示查詢碼。", "danger")
                    return redirect(url_for("case_detail", case_id=case_id))

                if not c.query_code_enc:
                    flash("此案件沒有可顯示的查詢碼（可能是舊資料）。建議按「重置查詢碼」。", "warning")
                    return redirect(url_for("case_detail", case_id=case_id))

                code_plain = decrypt_code(c.query_code_enc)
                flask_session["one_time_code"] = code_plain  # ✅ 沿用你已做好的「一次性顯示＋自動複製」機制
                flash("已驗證密碼，查詢碼將顯示一次並嘗試自動複製。", "success")
                return redirect(url_for("case_detail", case_id=case_id))

        one_time_code = flask_session.pop("one_time_code", None)

        return render_template(
            "case_detail.html",
            teacher=t,
            case=c,
            services=services,
            used_o=used_o,
            used_l=used_l,
            remaining_o=remaining_o,
            remaining_l=remaining_l,
            service_label=service_label,
            one_time_code=one_time_code,
            today=today,
        )

    # -------------------------
    # 用戶：年度匯出 CSV（跨年度用戶自己下載保存）
    # -------------------------
    @app.get("/teacher/export")
    def teacher_export():
        guard = require_login()
        if guard:
            return guard
        t = current_teacher()

        try:
            year = int(request.args.get("year") or date.today().year)
        except:
            year = date.today().year

        cases = Case.query.filter_by(teacher_id=t.id, fiscal_year=year).order_by(Case.student_name.asc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "年度", "用戶", "服務對象", "單位", "狀態",
            "項目", "開始日", "核給時數",
            "上課日期", "定向時數", "生活時數",
        ])

        for c in cases:
            svc_map = {s.service_type: s for s in c.services}
            # 逐筆 session 展開；若無 session 也輸出一列案件資訊
            if c.sessions:
                for sess in sorted(c.sessions, key=lambda x: x.session_date):
                    for stype, s in svc_map.items():
                        # 每列都帶上該項目資訊，方便做行政對帳
                        writer.writerow([
                            c.fiscal_year,
                            t.full_name,
                            c.student_name,
                            c.agency_name,
                            c.status,
                            service_label(stype),
                            s.start_date.isoformat(),
                            s.granted_hours,
                            sess.session_date.isoformat(),
                            sess.hours_orientation,
                            sess.hours_life
                        ])
            else:
                for stype, s in svc_map.items():
                    writer.writerow([
                        c.fiscal_year,
                        t.full_name,
                        c.student_name,
                        c.agency_name,
                        c.status,
                        service_label(stype),
                        s.start_date.isoformat(),
                        s.granted_hours,
                        "", "", ""
                    ])

        mem = io.BytesIO()
        mem.write(output.getvalue().encode("utf-8-sig"))
        mem.seek(0)

        filename = f"工作時數E指通_{t.full_name}_{year}.csv"
        return send_file(mem, as_attachment=True, download_name=filename, mimetype="text/csv")

    # -------------------------
    # 單位查詢：單位名稱＋服務對象姓名＋查詢碼
    # -------------------------
    @app.route("/lookup", methods=["GET", "POST"])
    def lookup():
        result = None
        if request.method == "POST":
            agency_name = (request.form.get("agency_name") or "").strip()
            student_name = (request.form.get("student_name") or "").strip()
            code = (request.form.get("code") or "").strip().upper()

            if not agency_name or not student_name or not code:
                flash("請輸入單位名稱、服務對象姓名與查詢碼。", "danger")
                return redirect(url_for("lookup"))

            # 清理輸入（先做！）
            agency_name = agency_name.replace("　", "").strip()
            student_name = student_name.replace("　", "").strip()

            # 單位模糊比對（包含關鍵字即可）
            candidates = Case.query.filter(
                Case.student_name == student_name,
                Case.agency_name.ilike(f"%{agency_name}%")
            ).all()
            matched = None
            for c in candidates:
                if check_password_hash(c.query_code_hash, code):
                    matched = c
                    break

            if not matched:
                flash("查詢失敗：資料不存在或查詢碼錯誤。", "danger")
                return redirect(url_for("lookup"))

            services = {s.service_type: s for s in matched.services}
            sessions = sorted(matched.sessions, key=lambda x: x.session_date)

            used_o = sum(s.hours_orientation for s in sessions)
            used_l = sum(s.hours_life for s in sessions)

            granted_o = services.get("orientation").granted_hours if "orientation" in services else 0.0
            granted_l = services.get("life").granted_hours if "life" in services else 0.0

            result = {
                "case": matched,
                "services": services,
                "sessions": sessions,
                "used_o": used_o,
                "used_l": used_l,
                "remaining_o": granted_o - used_o,
                "remaining_l": granted_l - used_l,
                "service_label": service_label,
            }

        return render_template("lookup.html", result=result)

    # =========================
    # ROUTES END
    # =========================

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("RAILWAY_ENVIRONMENT") is None  # 本機才開 debug
    app.run(host="0.0.0.0", port=port, debug=debug)
