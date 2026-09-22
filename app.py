import os
from datetime import datetime, date
from functools import wraps
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from dotenv import load_dotenv

load_dotenv()

import database
import ai_service

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret-change-me"),
    JSON_AS_ASCII=False,
)

database.init_db()


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login", next=request.path))
            if session.get("role") not in roles:
                flash("Bạn không có quyền thực hiện thao tác này.", "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


def is_admin():
    return session.get("role") == "admin"


def is_receptionist():
    return session.get("role") == "receptionist"


def is_barber():
    return session.get("role") == "barber"


@app.context_processor
def inject_globals():
    return {
        "current_user": database.get_user(session["user_id"]) if session.get("user_id") else None,
        "is_admin": is_admin(),
        "is_receptionist": is_receptionist(),
        "is_barber": is_barber(),
        "now": datetime.now(),
    }


@app.route("/")
@login_required
def home():
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = database.authenticate_user(username, password)
        if user:
            session.clear()
            session.update(
                user_id=user["id"],
                username=user["username"],
                full_name=user["full_name"],
                role=user["role"],
            )
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Tên đăng nhập hoặc mật khẩu không đúng.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        stats=database.dashboard_stats(),
        today_appointments=database.list_appointments(date.today().isoformat()),
        popular=database.popular_services(limit=5),
    )


@app.route("/customers", methods=["GET", "POST"])
@login_required
def customers():
    if request.method == "POST":
        payload = {
            "full_name": request.form.get("full_name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "email": request.form.get("email", "").strip(),
            "gender": request.form.get("gender", "").strip(),
            "birthday": request.form.get("birthday", "").strip(),
            "note": request.form.get("note", "").strip(),
        }
        if not payload["full_name"] or not payload["phone"]:
            flash("Họ tên và số điện thoại là bắt buộc.", "danger")
        else:
            database.create_customer(payload)
            flash("Đã thêm khách hàng.", "success")
        return redirect(url_for("customers"))

    q = request.args.get("q", "").strip()
    rows = database.list_customers(q)
    return render_template("customers.html", customers=rows, query=q)


@app.route("/customers/<int:customer_id>")
@login_required
def customer_detail(customer_id):
    customer = database.get_customer(customer_id)
    if not customer:
        return "Không tìm thấy khách hàng", 404
    return render_template(
        "customer_detail.html",
        customer=customer,
        history=database.customer_history(customer_id),
        appointments=database.list_appointments(customer_id=customer_id),
    )


@app.route("/customers/<int:customer_id>/edit", methods=["POST"])
@login_required
def edit_customer(customer_id):
    database.update_customer(
        customer_id,
        request.form.get("full_name", "").strip(),
        request.form.get("phone", "").strip(),
        request.form.get("email", "").strip(),
        request.form.get("gender", "").strip(),
        request.form.get("birthday", "").strip(),
        request.form.get("note", "").strip(),
    )
    flash("Đã cập nhật khách hàng.", "success")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/barbers")
@roles_required("admin", "receptionist")
def barbers():
    return render_template("barbers.html", barbers=database.list_barbers())


@app.route("/barbers", methods=["POST"])
@roles_required("admin")
def create_barber():
    database.create_barber(
        request.form.get("full_name", "").strip(),
        request.form.get("phone", "").strip(),
        request.form.get("specialty", "").strip(),
        request.form.get("experience", "").strip(),
        request.form.get("status", "active"),
    )
    flash("Đã thêm thợ.", "success")
    return redirect(url_for("barbers"))


@app.route("/services", methods=["GET", "POST"])
@login_required
def services():
    if request.method == "POST":
        database.create_service(
            request.form.get("name", "").strip(),
            request.form.get("category", "").strip(),
            request.form.get("description", "").strip(),
            int(request.form.get("duration_minutes", 30)),
            float(request.form.get("price", 0)),
        )
        flash("Đã thêm dịch vụ.", "success")
        return redirect(url_for("services"))
    return render_template("services.html", services=database.list_services())


@app.route("/appointments")
@login_required
def appointments():
    date_filter = request.args.get("date", "").strip()
    status = request.args.get("status", "").strip()
    return render_template(
        "appointments.html",
        appointments=database.list_appointments(date_filter=date_filter or None, status=status or None),
        customers=database.list_customers(),
        barbers=database.list_barbers(),
        services=database.list_services(),
        selected_date=date_filter,
        selected_status=status,
    )


@app.route("/appointments/create", methods=["POST"])
@roles_required("admin", "receptionist")
def create_appointment():
    customer_id = int(request.form["customer_id"])
    barber_id = int(request.form["barber_id"])
    service_ids = [int(x) for x in request.form.getlist("service_ids")]
    if not service_ids:
        flash("Hãy chọn ít nhất một dịch vụ.", "danger")
        return redirect(url_for("appointments"))
    appt_id = database.create_appointment(
        customer_id,
        barber_id,
        request.form["appointment_date"],
        request.form["start_time"],
        request.form.get("end_time", ""),
        request.form.get("note", "").strip(),
        service_ids,
    )
    flash(f"Đã tạo lịch hẹn #{appt_id}.", "success")
    return redirect(url_for("appointments"))


@app.route("/appointments/<int:appointment_id>/status", methods=["POST"])
@roles_required("admin", "receptionist", "barber")
def update_appointment_status(appointment_id):
    new_status = request.form.get("status", "").strip()
    if new_status not in {"Pending", "Confirmed", "Completed", "Cancelled"}:
        flash("Trạng thái không hợp lệ.", "danger")
    else:
        database.update_appointment_status(appointment_id, new_status)
        flash("Đã cập nhật trạng thái lịch hẹn.", "success")
    return redirect(url_for("appointments"))


@app.route("/invoices")
@roles_required("admin", "receptionist")
def invoices():
    return render_template("invoices.html", invoices=database.list_invoices())


@app.route("/invoices/create", methods=["POST"])
@roles_required("admin", "receptionist")
def create_invoice():
    appointment_id = int(request.form["appointment_id"])
    database.create_invoice(
        appointment_id,
        request.form.get("discount", 0),
        request.form.get("payment_method", "Cash"),
    )
    flash("Đã tạo hóa đơn.", "success")
    return redirect(url_for("invoices"))


@app.route("/history")
@login_required
def history():
    q = request.args.get("q", "").strip()
    return render_template("history.html", rows=database.search_history(q), query=q)


@app.route("/ai/recommendation")
@login_required
def ai_recommendation_page():
    return render_template(
        "ai_recommendation.html",
        customers=database.list_customers(),
        services=database.list_services(),
    )


@app.route("/ai/message")
@login_required
def ai_message_page():
    return render_template("ai_message.html", customers=database.list_customers())


@app.route("/ai/summary")
@login_required
def ai_summary_page():
    return render_template("ai_summary.html", customers=database.list_customers())


@app.route("/chat")
@login_required
def chat_page():
    return render_template("chat.html")


@app.route("/api/ai/recommend", methods=["POST"])
@login_required
def api_ai_recommend():
    data = request.get_json(silent=True) or {}
    customer_id = int(data.get("customer_id"))
    customer = database.get_customer(customer_id)
    if not customer:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    history = database.customer_history(customer_id)
    services = database.list_services(active_only=True)
    return jsonify(ai_service.recommend_service(customer, history, services))


@app.route("/api/ai/message", methods=["POST"])
@login_required
def api_ai_message():
    data = request.get_json(silent=True) or {}
    customer_id = int(data.get("customer_id"))
    customer = database.get_customer(customer_id)
    if not customer:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    history = database.customer_history(customer_id)
    services = database.list_services(active_only=True)
    return jsonify(ai_service.generate_message(customer, history, services))


@app.route("/api/ai/summary", methods=["POST"])
@login_required
def api_ai_summary():
    data = request.get_json(silent=True) or {}
    customer_id = int(data.get("customer_id"))
    customer = database.get_customer(customer_id)
    if not customer:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    return jsonify(ai_service.summarize_customer(customer, database.customer_history(customer_id)))


@app.route("/api/ai/chat", methods=["POST"])
@login_required
def api_ai_chat():
    try:
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()
        if not message:
            return jsonify({"error": "Vui lòng nhập câu hỏi."}), 400
        context = {
            "role": session.get("role"),
            "user_id": session.get("user_id"),
            "services": database.list_services(active_only=True),
        }
        result = ai_service.chat_salon(message, context)
        database.save_ai_chat(session["user_id"], message, result.get("reply", ""), result.get("mode", "ai"))
        return jsonify(result)
    except Exception as exc:
        app.logger.exception("AI chat error")
        return jsonify({"error": "Máy chủ AI gặp lỗi.", "detail": str(exc)}), 500


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="Không tìm thấy trang."), 404


@app.errorhandler(500)
def server_error(error):
    app.logger.exception("Unhandled server error: %s", error)
    return render_template("error.html", code=500, message="Có lỗi xảy ra trên máy chủ."), 500


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
