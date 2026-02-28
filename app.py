from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import csv
from flask import Response
from datetime import date

app = Flask(__name__)
app.secret_key = "your_secret_key"

# ------------------ Database ------------------
def get_db_connection():
    conn = sqlite3.connect("attendance.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS student (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        roll_no TEXT UNIQUE,
        department TEXT,
        semester TEXT,
        year TEXT,
        password TEXT
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no TEXT,
    date TEXT,
    status TEXT,     -- Present / Absent
    approved INTEGER  -- 0 = Pending, 1 = Approved
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ------------------ Login Required ------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "admin_logged_in" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ------------------ Routes ------------------

@app.route("/")
def home():
    return redirect(url_for("login"))

# -------- Admin Login --------
@app.route('/login', methods=['GET', 'POST'])
def login():    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == "admin" and password == "admin123":
            session["admin_logged_in"] = True
            return redirect('/dashboard')
        else:
            flash("Invalid username or password")

    return render_template('login.html')


# -------- Student Login --------
@app.route("/student_login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        roll_no = request.form["roll_no"]
        password = request.form["password"]

        conn = get_db_connection()

        student = conn.execute(
            "SELECT * FROM student WHERE roll_no=? AND password=?",
            (roll_no, password)
        ).fetchone()

        conn.close()

        if student:
            session["student"] = student["roll_no"]
            session["student_name"] = student["name"]
            return redirect(url_for("student_dashboard"))
        else:
            return render_template("student_login.html", error="Invalid Roll No or Password")

    return render_template("student_login.html")

@app.route('/student_dashboard')
def student_dashboard():
    # Check login session
    if 'student' not in session:
        return redirect(url_for('student_login'))

    roll_no = session['student']

    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ✅ Total approved attendance records
    cursor.execute("""
        SELECT COUNT(*) 
        FROM attendance 
        WHERE roll_no = ? AND approved = 1
    """, (roll_no,))
    total_days = cursor.fetchone()[0]

    # ✅ Present count
    cursor.execute("""
        SELECT COUNT(*) 
        FROM attendance 
        WHERE roll_no = ? AND status = 'Present' AND approved = 1
    """, (roll_no,))
    present_days = cursor.fetchone()[0]

    # ✅ Absent count
    absent_days = total_days - present_days

    # ✅ Attendance Percentage
    if total_days > 0:
        percentage = round((present_days / total_days) * 100, 2)
    else:
        percentage = 0

    conn.close()

    return render_template(
        "student_dashboard.html",
        total_days=total_days,
        present_days=present_days,
        absent_days=absent_days,
        percentage=percentage
    )
@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    if 'student' not in session:
        return redirect(url_for('student_login'))

    if request.method == 'POST':
        roll_no = session['student']
        today = date.today()

        conn = sqlite3.connect('attendance.db')
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO attendance (roll_no, date, status, approved)
            VALUES (?, ?, 'Present', 0)
        """, (roll_no, today))

        conn.commit()
        conn.close()

        return redirect(url_for('student_dashboard'))

    return render_template('mark_attendance.html')    

@app.route("/student_logout")
def student_logout():
    session.pop("student", None)
    session.pop("student_name", None)
    return redirect(url_for("student_login"))

# -------- Admin Approval Page --------

@app.route("/approve_attendance")
@login_required
def approve_attendance():
    conn = get_db_connection()

    pending = conn.execute("""
        SELECT * FROM attendance
        WHERE approved = 0
        ORDER BY date DESC
    """).fetchall()

    conn.close()

    return render_template("approve_attendance.html", pending=pending)


# -------- Approve Action --------

@app.route("/approve/<int:attendance_id>")
@login_required
def approve(attendance_id):
    conn = get_db_connection()

    conn.execute("""
        UPDATE attendance
        SET approved = 1
        WHERE id = ?
    """, (attendance_id,))

    conn.commit()
    conn.close()

    flash("Attendance Approved Successfully")
    return redirect(url_for("approve_attendance"))    

# -------- Dashboard --------
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db_connection()

    today = date.today().strftime("%Y-%m-%d")

    # Total Students
    total_students = conn.execute(
        "SELECT COUNT(*) FROM student"
    ).fetchone()[0]

    # Present Today
    present_today = conn.execute(
        "SELECT COUNT(*) FROM attendance WHERE date=? AND status='present'",
        (today,)
    ).fetchone()[0]

    # Absent Today
    absent_today = total_students - present_today

    # Overall Attendance
    total_attendance = conn.execute(
        "SELECT COUNT(*) FROM attendance"
    ).fetchone()[0]

    total_present = conn.execute(
        "SELECT COUNT(*) FROM attendance WHERE status='present'"
    ).fetchone()[0]

    overall_percentage = 0
    if total_attendance > 0:
        overall_percentage = round((total_present / total_attendance) * 100, 2)

    conn.close()

    return render_template(
        "dashboard.html",
        total_students=total_students,
        present_today=present_today,
        absent_today=absent_today,
        overall_percentage=overall_percentage
    )

# -------- Add Student --------
@app.route("/add_student", methods=["GET", "POST"])
@login_required
def add_student():
    if request.method == "POST":
        name = request.form.get("name")
        roll_no = request.form.get("roll_no")
        department = request.form.get("department")
        year = request.form.get("year")
        semester = request.form.get("semester")
        password = request.form.get("password")

        conn = get_db_connection()
        conn.execute("""
            INSERT INTO student
            (name, roll_no, department, semester, year, password)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, roll_no, department, semester, year, password))

        conn.commit()
        conn.close()

        return redirect(url_for("students"))

    return render_template("add_student.html")


# -------- View Students --------
@app.route("/students")
@login_required
def students():
    conn = get_db_connection()
    students = conn.execute("SELECT * FROM student").fetchall()
    conn.close()
    return render_template("students.html", students=students)

# --------- export -----------   
@app.route("/export")
@login_required
def export():
    conn = get_db_connection()

    department = request.args.get("department")
    year = request.args.get("year")
    semester = request.args.get("semester")

    query = """
        SELECT s.name, s.roll_no, s.department,
               s.year, s.semester,
               COUNT(a.id) as total,
               SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) as present
        FROM student s
        LEFT JOIN attendance a ON s.id = a.student_id
        WHERE 1=1
    """

    params = []

    if department:
        query += " AND s.department=?"
        params.append(department)

    if year:
        query += " AND s.year=?"
        params.append(year)

    if semester:
        query += " AND s.semester=?"
        params.append(semester)

    query += " GROUP BY s.id"

    records = conn.execute(query, params).fetchall()
    conn.close()

    def generate():
        yield "Name,Roll No,Department,Year,Semester,Total,Present,Absent\n"
        for r in records:
            total = r["total"] if r["total"] else 0
            present = r["present"] if r["present"] else 0
            absent = total - present

            yield f"{r['name']},{r['roll_no']},{r['department']},{r['year']},{r['semester']},{total},{present},{absent}\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=attendance_report.csv"}
    )

# ---------change password-----------
@app.route("/change_password/<int:student_id>", methods=["GET", "POST"])
@login_required
def change_password(student_id):
    conn = get_db_connection()

    if request.method == "POST":
        new_password = generate_password_hash(request.form["password"])
        conn.execute(
            "UPDATE student SET password = ? WHERE id = ?",
            (new_password, student_id)
        )
        conn.commit()
        conn.close()
        flash("Password updated successfully")
        return redirect(url_for("students"))

    student = conn.execute(
        "SELECT * FROM student WHERE id = ?",
        (student_id,)
    ).fetchone()
    conn.close()

    return render_template("change_password.html", student=student)


# -------- Mark Attendance --------
@app.route("/mark/<int:student_id>")
@login_required
def mark(student_id):
    conn = get_db_connection()
    today = datetime.now().date().isoformat()

    existing = conn.execute(
        "SELECT * FROM attendance WHERE student_id = ? AND date = ?",
        (student_id, today)
    ).fetchone()

    if existing:
        flash("Attendance already marked for today")
    else:
        current_time = datetime.now().strftime("%H:%M:%S")

        conn.execute(
            "INSERT INTO attendance (student_id, date, time, status) VALUES (?, ?, ?, ?)",
                (student_id, today, current_time, "present")
    )

        flash("Attendance marked successfully")

    conn.commit()
    conn.close()
    return redirect(url_for("students"))


# -------- Reports --------
@app.route("/reports", methods=["GET"])
@login_required
def reports():
    conn = get_db_connection()

    department = request.args.get("department")
    year = request.args.get("year")
    semester = request.args.get("semester")

    query = """
        SELECT s.id, s.name, s.roll_no,
               s.department, s.year, s.semester
        FROM student s
        WHERE 1=1
    """

    params = []

    if department:
        query += " AND s.department = ?"
        params.append(department)

    if year:
        query += " AND s.year = ?"
        params.append(year)

    if semester:
        query += " AND s.semester = ?"
        params.append(semester)

    students = conn.execute(query, params).fetchall()

    report_data = []

    for student in students:

        # Total attendance records
        total = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE student_id=?",
            (student["id"],)
        ).fetchone()[0]

        # Present count
        present = conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE student_id=? AND status='present'",
            (student["id"],)
        ).fetchone()[0]

        # Absent calculation
        absent = total - present

        # Attendance Percentage
        percentage = 0
        if total > 0:
            percentage = round((present / total) * 100, 2)

        report_data.append({
            "name": student["name"],
            "roll_no": student["roll_no"],
            "department": student["department"],
            "year": student["year"],
            "semester": student["semester"],
            "total": total,
            "present": present,
            "absent": absent,
            "percentage": percentage
        })

    conn.close()

    return render_template("reports.html", report_data=report_data)


# -------- Logout --------
@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("login"))


# ------------------ Main ------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)

