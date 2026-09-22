from pathlib import Path
from datetime import datetime
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "salon_system.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'receptionist',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            email TEXT,
            gender TEXT,
            birthday TEXT,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS barbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT,
            specialty TEXT,
            experience TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            duration_minutes INTEGER NOT NULL DEFAULT 30,
            price REAL NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            barber_id INTEGER NOT NULL,
            appointment_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY(barber_id) REFERENCES barbers(id) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS appointment_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            price REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER UNIQUE NOT NULL,
            customer_id INTEGER NOT NULL,
            subtotal REAL NOT NULL DEFAULT 0,
            discount REAL NOT NULL DEFAULT 0,
            total REAL NOT NULL DEFAULT 0,
            payment_method TEXT DEFAULT 'Cash',
            payment_status TEXT DEFAULT 'Paid',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL DEFAULT 0,
            amount REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS customer_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            appointment_id INTEGER,
            service_id INTEGER,
            hair_style TEXT,
            hair_color TEXT,
            customer_note TEXT,
            barber_note TEXT,
            result TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS ai_chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT NOT NULL,
            response TEXT NOT NULL,
            mode TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date);
        CREATE INDEX IF NOT EXISTS idx_history_customer ON customer_history(customer_id);
        """
    )
    seed_data(conn)
    conn.commit()
    conn.close()


def seed_data(conn):
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute("INSERT INTO users(username,password_hash,full_name,role) VALUES (?,?,?,?)", ("admin", generate_password_hash("123456"), "Quản trị viên", "admin"))
        conn.execute("INSERT INTO users(username,password_hash,full_name,role) VALUES (?,?,?,?)", ("le_tan", generate_password_hash("123456"), "Lê Tân", "receptionist"))
        conn.execute("INSERT INTO users(username,password_hash,full_name,role) VALUES (?,?,?,?)", ("tho01", generate_password_hash("123456"), "Nguyễn Minh Quân", "barber"))

    if conn.execute("SELECT COUNT(*) FROM barbers").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO barbers(full_name,phone,specialty,experience,status) VALUES (?,?,?,?,?)",
            [
                ("Nguyễn Minh Quân", "0901000001", "Cắt tạo kiểu", "6 năm", "active"),
                ("Trần Duy Long", "0901000002", "Nhuộm", "5 năm", "active"),
                ("Lê Hoàng Nam", "0901000003", "Uốn và phục hồi", "7 năm", "active"),
            ],
        )

    if conn.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO services(name,category,description,duration_minutes,price) VALUES (?,?,?,?,?)",
            [
                ("Cắt tóc nam", "Haircut", "Cắt và tạo kiểu cơ bản", 45, 120000),
                ("Cắt layer", "Haircut", "Cắt layer theo khuôn mặt", 60, 180000),
                ("Nhuộm tóc", "Color", "Nhuộm theo màu khách chọn", 150, 650000),
                ("Uốn tóc", "Styling", "Uốn tạo kiểu", 180, 850000),
                ("Gội dưỡng tóc", "Care", "Gội và dưỡng tóc", 45, 150000),
                ("Phục hồi tóc", "Treatment", "Phục hồi tóc hư tổn", 90, 450000),
            ],
        )

    if conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO customers(full_name,phone,email,note) VALUES (?,?,?,?)",
            [
                ("Nguyễn Văn An", "0912000001", "an@example.com", "Thích kiểu layer, màu nâu."),
                ("Trần Thị Bình", "0912000002", "binh@example.com", "Ưa tóc ngắn và dễ chăm sóc."),
                ("Lê Minh Châu", "0912000003", "chau@example.com", "Từng nhuộm tóc, tóc hơi khô."),
            ],
        )


def authenticate_user(username, password):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row and check_password_hash(row["password_hash"], password) else None


def get_user(user_id):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def dashboard_stats():
    conn = get_db_connection()
    today = datetime.now().date().isoformat()
    stats = {
        "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "appointments_today": conn.execute("SELECT COUNT(*) FROM appointments WHERE appointment_date=?", (today,)).fetchone()[0],
        "pending": conn.execute("SELECT COUNT(*) FROM appointments WHERE status='Pending'").fetchone()[0],
        "revenue_month": conn.execute("SELECT COALESCE(SUM(total),0) FROM invoices WHERE substr(created_at,1,7)=?", (datetime.now().strftime('%Y-%m'),)).fetchone()[0],
    }
    conn.close()
    return stats


def create_customer(p):
    conn = get_db_connection()
    conn.execute("INSERT INTO customers(full_name,phone,email,gender,birthday,note) VALUES (?,?,?,?,?,?)", (p["full_name"],p["phone"],p.get("email"),p.get("gender"),p.get("birthday"),p.get("note")))
    conn.commit(); conn.close()


def list_customers(q=""):
    conn = get_db_connection()
    if q:
        rows = conn.execute("SELECT * FROM customers WHERE full_name LIKE ? OR phone LIKE ? OR email LIKE ? ORDER BY id DESC", (f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    else:
        rows = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    conn.close(); return [dict(r) for r in rows]


def get_customer(customer_id):
    conn = get_db_connection(); row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone(); conn.close(); return dict(row) if row else None


def update_customer(customer_id, full_name, phone, email, gender, birthday, note):
    conn = get_db_connection(); conn.execute("UPDATE customers SET full_name=?,phone=?,email=?,gender=?,birthday=?,note=? WHERE id=?", (full_name,phone,email,gender,birthday,note,customer_id)); conn.commit(); conn.close()


def list_barbers():
    conn = get_db_connection(); rows = conn.execute("SELECT * FROM barbers ORDER BY full_name").fetchall(); conn.close(); return [dict(r) for r in rows]


def create_barber(full_name, phone, specialty, experience, status):
    conn=get_db_connection(); conn.execute("INSERT INTO barbers(full_name,phone,specialty,experience,status) VALUES (?,?,?,?,?)",(full_name,phone,specialty,experience,status)); conn.commit(); conn.close()


def list_services(active_only=False):
    conn=get_db_connection()
    sql="SELECT * FROM services"
    params=[]
    if active_only:
        sql += " WHERE status='active'"
    sql += " ORDER BY category,name"
    rows=conn.execute(sql,params).fetchall(); conn.close(); return [dict(r) for r in rows]


def create_service(name, category, description, duration_minutes, price):
    conn=get_db_connection(); conn.execute("INSERT INTO services(name,category,description,duration_minutes,price) VALUES (?,?,?,?,?)",(name,category,description,duration_minutes,price)); conn.commit(); conn.close()


def create_appointment(customer_id, barber_id, appointment_date, start_time, end_time, note, service_ids):
    conn=get_db_connection()
    overlap=conn.execute("SELECT COUNT(*) FROM appointments WHERE barber_id=? AND appointment_date=? AND status NOT IN ('Cancelled','Completed') AND ((start_time < ? AND COALESCE(end_time,start_time) > ?) OR (start_time >= ? AND start_time < COALESCE(?,start_time)))", (barber_id,appointment_date,end_time,start_time,start_time,end_time)).fetchone()[0]
    if overlap:
        conn.close(); raise ValueError("Thợ đã có lịch trùng trong khoảng thời gian này.")
    cur=conn.execute("INSERT INTO appointments(customer_id,barber_id,appointment_date,start_time,end_time,status,note) VALUES (?,?,?,?,?,?,?)",(customer_id,barber_id,appointment_date,start_time,end_time,"Pending",note))
    appointment_id=cur.lastrowid
    for service_id in service_ids:
        row=conn.execute("SELECT price FROM services WHERE id=?",(service_id,)).fetchone()
        if not row: continue
        conn.execute("INSERT INTO appointment_services(appointment_id,service_id,quantity,price) VALUES (?,?,?,?)",(appointment_id,service_id,1,row["price"]))
    conn.commit(); conn.close(); return appointment_id


def list_appointments(date_filter=None, status=None, customer_id=None):
    conn=get_db_connection()
    sql="""SELECT a.*, c.full_name customer_name, c.phone customer_phone, b.full_name barber_name,
           COALESCE((SELECT SUM(aps.quantity*aps.price) FROM appointment_services aps WHERE aps.appointment_id=a.id),0) amount
           FROM appointments a JOIN customers c ON c.id=a.customer_id JOIN barbers b ON b.id=a.barber_id WHERE 1=1"""
    params=[]
    if date_filter: sql += " AND a.appointment_date=?"; params.append(date_filter)
    if status: sql += " AND a.status=?"; params.append(status)
    if customer_id: sql += " AND a.customer_id=?"; params.append(customer_id)
    sql += " ORDER BY a.appointment_date DESC,a.start_time DESC"
    rows=conn.execute(sql,params).fetchall(); conn.close(); return [dict(r) for r in rows]


def update_appointment_status(appointment_id, status):
    conn=get_db_connection(); conn.execute("UPDATE appointments SET status=? WHERE id=?",(status,appointment_id))
    if status == "Completed":
        appt=conn.execute("SELECT * FROM appointments WHERE id=?",(appointment_id,)).fetchone()
        services=conn.execute("SELECT service_id FROM appointment_services WHERE appointment_id=? LIMIT 1",(appointment_id,)).fetchone()
        if appt and services:
            conn.execute("INSERT INTO customer_history(customer_id,appointment_id,service_id,result) VALUES (?,?,?,?)",(appt["customer_id"],appointment_id,services["service_id"],"Hoàn thành dịch vụ"))
    conn.commit(); conn.close()


def create_invoice(appointment_id, discount, payment_method):
    conn=get_db_connection(); appt=conn.execute("SELECT customer_id FROM appointments WHERE id=?",(appointment_id,)).fetchone()
    if not appt: conn.close(); raise ValueError("Không tìm thấy lịch hẹn.")
    items=conn.execute("SELECT * FROM appointment_services WHERE appointment_id=?",(appointment_id,)).fetchall()
    subtotal=sum(float(x["price"])*int(x["quantity"]) for x in items)
    discount=float(discount or 0); total=max(0, subtotal-discount)
    cur=conn.execute("INSERT INTO invoices(appointment_id,customer_id,subtotal,discount,total,payment_method,payment_status) VALUES (?,?,?,?,?,?,?)",(appointment_id,appt["customer_id"],subtotal,discount,total,payment_method,"Paid"))
    invoice_id=cur.lastrowid
    for x in items: conn.execute("INSERT INTO invoice_items(invoice_id,service_id,quantity,unit_price,amount) VALUES (?,?,?,?,?)",(invoice_id,x["service_id"],x["quantity"],x["price"],x["price"]*x["quantity"]))
    conn.commit(); conn.close()


def list_invoices():
    conn=get_db_connection(); rows=conn.execute("SELECT i.*, c.full_name customer_name FROM invoices i JOIN customers c ON c.id=i.customer_id ORDER BY i.id DESC").fetchall(); conn.close(); return [dict(r) for r in rows]


def customer_history(customer_id):
    conn=get_db_connection(); rows=conn.execute("""SELECT h.*, s.name service_name, a.appointment_date FROM customer_history h LEFT JOIN services s ON s.id=h.service_id LEFT JOIN appointments a ON a.id=h.appointment_id WHERE h.customer_id=? ORDER BY h.created_at DESC""",(customer_id,)).fetchall(); conn.close(); return [dict(r) for r in rows]


def search_history(q=""):
    conn=get_db_connection()
    if q:
        rows=conn.execute("""SELECT h.*, c.full_name customer_name, s.name service_name FROM customer_history h JOIN customers c ON c.id=h.customer_id LEFT JOIN services s ON s.id=h.service_id WHERE c.full_name LIKE ? OR s.name LIKE ? OR h.hair_style LIKE ? OR h.hair_color LIKE ? ORDER BY h.created_at DESC""",(f"%{q}%",f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    else:
        rows=conn.execute("""SELECT h.*, c.full_name customer_name, s.name service_name FROM customer_history h JOIN customers c ON c.id=h.customer_id LEFT JOIN services s ON s.id=h.service_id ORDER BY h.created_at DESC""").fetchall()
    conn.close(); return [dict(r) for r in rows]


def popular_services(limit=5):
    conn=get_db_connection(); rows=conn.execute("""SELECT s.name, COUNT(*) count FROM appointment_services aps JOIN services s ON s.id=aps.service_id GROUP BY s.id ORDER BY count DESC LIMIT ?""",(limit,)).fetchall(); conn.close(); return [dict(r) for r in rows]


def save_ai_chat(user_id, message, response, mode):
    conn=get_db_connection(); conn.execute("INSERT INTO ai_chat_history(user_id,message,response,mode) VALUES (?,?,?,?)",(user_id,message,response,mode)); conn.commit(); conn.close()
