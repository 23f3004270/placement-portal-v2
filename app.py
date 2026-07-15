import sqlite3
import os
import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt, get_jwt_identity
from werkzeug.security import check_password_hash, generate_password_hash
from flask_caching import Cache
from celery import Celery

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = 'ezplacekey2026'
jwt = JWTManager(app)

# Local Mailhog SMTP
MAILHOG_HOST = "localhost"
MAILHOG_PORT = 1025
SYSTEM_SENDER = "placement-cell@ezplace.com"

# Cache setup
app.config['CACHE_TYPE'] = 'RedisCache'
app.config['CACHE_REDIS_URL'] = 'redis://localhost:6379/0'
cache = Cache(app)

# Celery config
def make_celery(app):
    redis_url = 'redis://localhost:6379/0'
    celery = Celery(app.import_name, broker=redis_url, backend=redis_url)
    celery.conf.worker_pool = 'solo'
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
                
    celery.Task = ContextTask
    return celery

celery = make_celery(app)

# Database helper
def get_db():
    conn = sqlite3.connect('placement_portal.sqlite3')
    conn.row_factory = sqlite3.Row
    return conn

# Async CSV export
@celery.task(name='app.export_applications_csv')
def export_applications_csv(user_id, role):
    conn = get_db()
    cur = conn.cursor()
    
    if role == 'Student':
        cur.execute("SELECT id FROM students WHERE user_id = ?", (user_id,))
        student = cur.fetchone()
        if not student: 
            conn.close()
            return
            
        sid = student['id']
        cur.execute("""
            SELECT j.title, c.name as company_name, a.status, a.remarks, a.applied_date 
            FROM applications a
            JOIN job_positions j ON a.job_id = j.id
            JOIN companies c ON j.company_id = c.id 
            WHERE a.student_id = ?
        """, (sid,))
        
        rows = cur.fetchall()
        filename = f"static/exports/student_{user_id}_applications.csv"
        
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Job Title', 'Company Name', 'Status', 'Remarks', 'Applied Date'])
            for row in rows:
                writer.writerow([row['title'], row['company_name'], row['status'], row['remarks'], row['applied_date']])
                
    elif role == 'Company':
        cur.execute("SELECT id FROM companies WHERE user_id = ?", (user_id,))
        company = cur.fetchone()
        if not company:
            conn.close()
            return
            
        cid = company['id']
        cur.execute("""
            SELECT j.title, s.name as student_name, a.status, a.remarks, a.applied_date
            FROM applications a
            JOIN job_positions j ON a.job_id = j.id
            JOIN students s ON a.student_id = s.id
            WHERE j.company_id = ?
        """, (cid,))
        
        rows = cur.fetchall()
        filename = f"static/exports/company_{user_id}_applications.csv"
        
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Job Title', 'Student Name', 'Status', 'Remarks', 'Applied Date'])
            for row in rows:
                writer.writerow([row['title'], row['student_name'], row['status'], row['remarks'], row['applied_date']])
                
    conn.close()

# Automated Mailhog Email Dispatcher
@celery.task(name='app.send_interview_reminders')
def send_interview_reminders():
    conn = get_db()
    cur = conn.cursor()
    # Query scheduled interviews missing the sent token
    cur.execute("""
        SELECT a.id as app_id, s.name, u.email as student_email, j.title, c.name as company_name, a.remarks
        FROM applications a
        JOIN students s ON a.student_id = s.id
        JOIN users u ON s.user_id = u.id
        JOIN job_positions j ON a.job_id = j.id
        JOIN companies c ON j.company_id = c.id
        WHERE a.status = 'Interview' AND (a.remarks NOT LIKE '%[Mail Dispatched]%')
    """)
    reminders = cur.fetchall()
    
    if len(reminders) > 0:
        try:
            # link mailhog
            server = smtplib.SMTP(MAILHOG_HOST, MAILHOG_PORT)
            
            for r in reminders:
                msg = MIMEMultipart()
                msg['From'] = SYSTEM_SENDER
                msg['To'] = r['student_email']
                msg['Subject'] = f"🚨 CONFIRMED: Interview Scheduled with {r['company_name']}"
                
                # parse text
                booking_details = r['remarks']
                
                body_content = f"""
                <html>
                <body style="font-family: Segoe UI, Arial, sans-serif; background-color: #f7f9fa; padding: 20px; color: #333;">
                    <div style="max-width: 600px; margin: auto; background: #fff; border: 1px solid #e1e4e6; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                        <h2 style="color: #0dcaf0; margin-top: 0;">EZPlace Interview Call Letter</h2>
                        <p>Hi <strong>{r['name']}</strong>,</p>
                        <p>Great news! Your application layout for the <strong>{r['title']}</strong> position has been approved, and an interview slot has been officially locked in.</p>
                        
                        <div style="background-color: #f1f3f5; padding: 15px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #0dcaf0;">
                            <h4 style="margin: 0 0 10px 0; color: #495057;">🗓️ Booking Summary Details:</h4>
                            <p style="margin: 4px 0;">{booking_details}</p>
                        </div>
                        
                        <p>Please log into your student workspace profile to review target specifications or clear prerequisites beforehand.</p>
                        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;" />
                        <p style="font-size: 12px; color: #868e96; margin-bottom: 0;">Automated message dispatched via Celery Engine & local Mailhog SMTP network.</p>
                    </div>
                </body>
                </html>
                """
                msg.attach(MIMEText(body_content, 'html'))
                server.sendmail(SYSTEM_SENDER, r['student_email'], msg.as_string())
                print(f"[MAILHOG WORKER] Dispatched confirmation payload routing to {r['student_email']}")
                
                updated_remarks = f"{r['remarks']} [Mail Dispatched]".strip()
                cur.execute("UPDATE applications SET remarks = ? WHERE id = ?", (updated_remarks, r['app_id']))
                
            server.quit()
            conn.commit()
        except Exception as e:
            print(f"[MAILHOG WORKER] SMTP server interaction crashed out: {str(e)}")
            
    conn.close()

# monthly reports
@celery.task(name='app.generate_monthly_placement_reports')
def generate_monthly_placement_reports():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM companies")
    companies = cur.fetchall()
    
    for comp in companies:
        cur.execute("SELECT COUNT(*) FROM job_positions WHERE company_id = ?", (comp['id'],))
        total_jobs = cur.fetchone()[0]
        
        cur.execute("""
            SELECT COUNT(*) FROM applications a
            JOIN job_positions j ON a.job_id = j.id
            WHERE j.company_id = ?
        """, (comp['id'],))
        total_apps = cur.fetchone()[0]
        
        cur.execute("""
            SELECT COUNT(*) FROM applications a
            JOIN job_positions j ON a.job_id = j.id
            WHERE j.company_id = ? AND a.status = 'Placed'
        """, (comp['id'],))
        total_placements = cur.fetchone()[0]
        
        report_content = f"""
        <html>
        <head><title>Monthly Placement Report - {comp['name']}</title></head>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f9;">
            <h2>Monthly Performance Analytics Report for {comp['name']}</h2>
            <hr/>
            <p><strong>Total Job Postings Created:</strong> {total_jobs}</p>
            <p><strong>Total Received Applications:</strong> {total_apps}</p>
            <p><strong>Total Confirmed Placements:</strong> {total_placements}</p>
        </body>
        </html>
        """
        filename = f"static/reports/company_{comp['id']}_monthly_report.html"
        with open(filename, 'w') as f:
            f.write(report_content)
        print(f"[REPORT ENGINE] Generated monthly report for {comp['name']} at {filename}")
    conn.close()

# Beat config
celery.conf.beat_schedule = {
    'send-interview-reminders-every-minute': {
        'task': 'app.send_interview_reminders',
        'schedule': 60.0,
    },
    'generate-monthly-reports-every-five-minutes': {
        'task': 'app.generate_monthly_placement_reports',
        'schedule': 300.0,
    },
}

# Web views
@app.route('/')
def index(): return render_template('login.html')

@app.route('/admin')
def admin_page(): return render_template('admin.html')

@app.route('/company')
def company_page(): return render_template('company.html')

@app.route('/student')
def student_page(): return render_template('student.html')

# API Endpoints
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (data['email'],))
    user = cur.fetchone()
    conn.close()
    
    if user and check_password_hash(user['password'], data['password']):
        if not user['is_active']: return jsonify({"msg": "account deactivated"}), 403
        token = create_access_token(identity=str(user['id']), additional_claims={"role": user['role']})
        return jsonify({"token": token, "role": user['role']})
    return jsonify({"msg": "invalid credentials"}), 401

@app.route('/api/register/student', methods=['POST'])
def reg_student():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name or any(char.isdigit() for char in name):
        return jsonify({"msg": "name cannot contain numbers"}), 400
        
    conn = get_db()
    cur = conn.cursor()
    try:
        hashed_pw = generate_password_hash(data['password'])
        cur.execute("INSERT INTO users (email, password, role) VALUES (?, ?, 'Student')", (data['email'], hashed_pw))
        user_id = cur.lastrowid
        cur.execute("INSERT INTO students (user_id, name) VALUES (?, ?)", (user_id, name))
        conn.commit()
    except sqlite3.IntegrityError: return jsonify({"msg": "email exists"}), 400
    finally: conn.close()
    return jsonify({"msg": "registered"}), 201

@app.route('/api/register/company', methods=['POST'])
def reg_company():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name or any(char.isdigit() for char in name):
        return jsonify({"msg": "company name cannot contain numbers"}), 400
        
    conn = get_db()
    cur = conn.cursor()
    try:
        hashed_pw = generate_password_hash(data['password'])
        cur.execute("INSERT INTO users (email, password, role) VALUES (?, ?, 'Company')", (data['email'], hashed_pw))
        user_id = cur.lastrowid
        cur.execute("INSERT INTO companies (user_id, name) VALUES (?, ?)", (user_id, name))
        conn.commit()
    except sqlite3.IntegrityError: return jsonify({"msg": "email exists"}), 400
    finally: conn.close()
    return jsonify({"msg": "registered"}), 201

@app.route('/api/export/trigger', methods=['POST'])
@jwt_required()
def trigger_export():
    uid = int(get_jwt_identity())
    role = get_jwt().get('role')
    filename = f"static/exports/student_{uid}_applications.csv" if role == 'Student' else f"static/exports/company_{uid}_applications.csv"
    if os.path.exists(filename): os.remove(filename)
    export_applications_csv.delay(uid, role)
    return jsonify({"msg": "Export task started"})

@app.route('/api/export/status', methods=['GET'])
@jwt_required()
def check_export_status():
    uid = int(get_jwt_identity())
    role = get_jwt().get('role')
    filename = f"static/exports/student_{uid}_applications.csv" if role == 'Student' else f"static/exports/company_{uid}_applications.csv"
    if os.path.exists(filename): return jsonify({"status": "completed", "download_url": f"/{filename}"})
    return jsonify({"status": "pending"})

@app.route('/api/admin/stats', methods=['GET'])
@jwt_required()
def admin_stats():
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM students"); s_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM companies"); c_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM job_positions"); j_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM applications"); a_count = cur.fetchone()[0]
    conn.close()
    return jsonify({"students": s_count, "companies": c_count, "jobs": j_count, "applications": a_count})

@app.route('/api/admin/companies', methods=['GET'])
@jwt_required()
def admin_companies():
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    search = request.args.get('search', '')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT c.*, u.is_active FROM companies c JOIN users u ON c.user_id = u.id WHERE c.name LIKE ?", (f'%{search}%',))
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/admin/companies/<int:cid>/<action>', methods=['POST'])
@jwt_required()
def admin_manage_company(cid, action):
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    conn = get_db()
    cur = conn.cursor()
    if action == 'approve': cur.execute("UPDATE companies SET is_approved = 1 WHERE id = ?", (cid,))
    elif action == 'reject': cur.execute("UPDATE companies SET is_approved = 0 WHERE id = ?", (cid,))
    elif action == 'deactivate':
        cur.execute("SELECT user_id FROM companies WHERE id = ?", (cid,)); uid = cur.fetchone()['user_id']
        cur.execute("UPDATE users SET is_active = 0 WHERE id = ?", (uid,))
    elif action == 'activate':
        cur.execute("SELECT user_id FROM companies WHERE id = ?", (cid,)); uid = cur.fetchone()['user_id']
        cur.execute("UPDATE users SET is_active = 1 WHERE id = ?", (uid,))
    elif action == 'delete':
        cur.execute("SELECT user_id FROM companies WHERE id = ?", (cid,)); row = cur.fetchone()
        if row:
            uid = row['user_id']
            cur.execute("DELETE FROM applications WHERE job_id IN (SELECT id FROM job_positions WHERE company_id = ?)", (cid,))
            cur.execute("DELETE FROM job_positions WHERE company_id = ?", (cid,))
            cur.execute("DELETE FROM companies WHERE id = ?", (cid,))
            cur.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit(); conn.close()
    return jsonify({"msg": "success"})

@app.route('/api/admin/students', methods=['GET'])
@jwt_required()
def admin_students():
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    search = request.args.get('search', '')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT s.*, (s.ug_degree || ' (' || s.ug_specialization || ')') AS education, u.is_active FROM students s JOIN users u ON s.user_id = u.id WHERE s.name LIKE ? OR s.skills LIKE ?", (f'%{search}%', f'%{search}%'))
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/admin/students/<int:sid>/<action>', methods=['POST'])
@jwt_required()
def admin_manage_student(sid, action):
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM students WHERE id = ?", (sid,)); row = cur.fetchone()
    if not row: conn.close(); return jsonify({"msg": "student not found"}), 404
    uid = row['user_id']
    if action == 'deactivate': cur.execute("UPDATE users SET is_active = 0 WHERE id = ?", (uid,))
    elif action == 'activate': cur.execute("UPDATE users SET is_active = 1 WHERE id = ?", (uid,))
    elif action == 'delete':
        cur.execute("DELETE FROM applications WHERE student_id = ?", (sid,))
        cur.execute("DELETE FROM students WHERE id = ?", (sid,))
        cur.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit(); conn.close()
    return jsonify({"msg": "success"})

@app.route('/api/admin/jobs', methods=['GET'])
@jwt_required()
def admin_jobs():
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT j.*, c.name as company_name FROM job_positions j JOIN companies c ON j.company_id = c.id")
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/admin/jobs/<int:jid>/<action>', methods=['POST'])
@jwt_required()
def admin_manage_job(jid, action):
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    conn = get_db()
    cur = conn.cursor()
    if action == 'approve': cur.execute("UPDATE job_positions SET status = 'Active' WHERE id = ?", (jid,))
    elif action == 'reject': cur.execute("UPDATE job_positions SET status = 'Rejected' WHERE id = ?", (jid,))
    conn.commit(); conn.close()
    return jsonify({"msg": "success"})

@app.route('/api/company/data', methods=['GET'])
@jwt_required()
def company_data():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, is_approved FROM companies WHERE user_id = ?", (int(get_jwt_identity()),))
    comp = cur.fetchone()
    if not comp: conn.close(); return jsonify({"is_approved": False}), 404
    if not comp['is_approved']: conn.close(); return jsonify({"is_approved": False})
    cur.execute("SELECT * FROM job_positions WHERE company_id = ?", (comp['id'],))
    jobs = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify({"is_approved": True, "name": comp['name'], "jobs": jobs, "company_id": comp['id']})

@app.route('/api/company/jobs', methods=['POST'])
@jwt_required()
def company_post_job():
    data = request.get_json()
    title = data.get('title', '').strip()
    if not title or title.isdigit(): return jsonify({"msg": "job title cannot be numeric only or empty"}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_approved FROM companies WHERE id = ?", (data['company_id'],))
    comp = cur.fetchone()
    if not comp or not comp['is_approved']: conn.close(); return jsonify({"msg": "company profile not approved"}), 403
    cur.execute("INSERT INTO job_positions (company_id, title, description, salary, skills_required, status) VALUES (?, ?, ?, ?, ?, 'Pending')", (data['company_id'], title, data['description'], int(data['salary']), data['skills_required']))
    conn.commit(); conn.close()
    return jsonify({"msg": "posted"})

@app.route('/api/company/jobs/<int:jid>/applicants', methods=['GET'])
@jwt_required()
def company_applicants(jid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT a.id as app_id, a.status, a.remarks, s.name, s.skills, s.resume_link, s.ug_degree, s.ug_specialization, s.pg_degree, s.pg_specialization, s.cgpa FROM applications a JOIN students s ON a.student_id = s.id WHERE a.job_id = ?", (jid,))
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

# Explicit Interview Booking Management Logic Route
@app.route('/api/company/applications/<int:aid>/status', methods=['PUT'])
@jwt_required()
def company_update_status(aid):
    data = request.get_json()
    status_target = data.get('status')
    custom_remarks = data.get('remarks', '')
    
    conn = get_db()
    cur = conn.cursor()
    
    # Process structured variables when booking a full calendar slot workflow
    if status_target == 'Interview':
        booking_date = data.get('interview_date', 'TBD')
        booking_time = data.get('interview_time', 'TBD')
        booking_link = data.get('interview_link', 'Dashboard Meeting Link')
        
        # Structure payload text inside remarks column
        custom_remarks = f"Scheduled: {booking_date} at {booking_time} | Platform Link: {booking_link}"

    cur.execute("UPDATE applications SET status = ?, remarks = ? WHERE id = ?", (status_target, custom_remarks, aid))
    conn.commit()
    conn.close()
    return jsonify({"msg": "updated"})

@app.route('/api/student/profile', methods=['GET', 'PUT'])
@jwt_required()
def student_profile():
    conn = get_db()
    cur = conn.cursor()
    uid = int(get_jwt_identity())
    if request.method == 'GET':
        cur.execute("SELECT * FROM students WHERE user_id = ?", (uid,))
        res = dict(cur.fetchone()); conn.close(); return jsonify(res)
    data = request.get_json()
    if not all([data.get('name'), data.get('ug_degree'), data.get('ug_specialization'), data.get('cgpa'), data.get('skills'), data.get('resume_link')]): 
        return jsonify({"msg": "all required profile fields must be completed"}), 400
    cur.execute("UPDATE students SET name=?, ug_degree=?, ug_specialization=?, pg_degree=?, pg_specialization=?, cgpa=?, skills=?, resume_link=? WHERE user_id=?", (data['name'], data['ug_degree'], data['ug_specialization'], data.get('pg_degree'), data.get('pg_specialization'), float(data['cgpa']), data['skills'], data['resume_link'], uid))
    conn.commit(); conn.close()
    return jsonify({"msg": "updated"})

@app.route('/api/student/jobs', methods=['GET'])
@jwt_required()
@cache.cached(timeout=30, query_string=True)
def student_jobs():
    search = request.args.get('search', '')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT j.*, c.name as company_name FROM job_positions j JOIN companies c ON j.company_id = c.id WHERE j.status = 'Active' AND c.is_approved = 1 AND (j.title LIKE ? OR c.name LIKE ?)", (f'%{search}%', f'%{search}%'))
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/student/apply', methods=['POST'])
@jwt_required()
def student_apply():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE user_id = ?", (int(get_jwt_identity()),))
    student = cur.fetchone(); sid = student['id']
    if not all([student['name'], student['ug_degree'], student['ug_specialization'], student['cgpa'], student['skills'], student['resume_link']]): 
        conn.close(); return jsonify({"msg": "complete your profile details before applying"}), 400
    cur.execute("SELECT id FROM applications WHERE student_id = ? AND job_id = ?", (sid, data['job_id']))
    if cur.fetchone(): conn.close(); return jsonify({"msg": "already applied to this job"}), 400
    cur.execute("INSERT INTO applications (student_id, job_id, status) VALUES (?, ?, 'Applied')", (sid, data['job_id']))
    conn.commit(); conn.close()
    return jsonify({"msg": "applied"}), 201

@app.route('/api/student/applications', methods=['GET'])
@jwt_required()
def student_applications():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM students WHERE user_id = ?", (int(get_jwt_identity()),))
    sid = cur.fetchone()['id']
    cur.execute("SELECT a.*, j.title, j.skills_required, c.name as company_name FROM applications a JOIN job_positions j ON a.job_id = j.id JOIN companies c ON j.company_id = c.id WHERE a.student_id = ?", (sid,))
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/student/applications/<int:aid>/accept', methods=['PUT'])
@jwt_required()
def student_accept_offer(aid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM students WHERE user_id = ?", (int(get_jwt_identity()),))
    student = cur.fetchone()
    if not student: conn.close(); return jsonify({"msg": "student not found"}), 404
    cur.execute("SELECT status FROM applications WHERE id = ? AND student_id = ?", (aid, student['id']))
    app_row = cur.fetchone()
    if not app_row: conn.close(); return jsonify({"msg": "application record not found"}), 404
    if app_row['status'] != 'Offer': conn.close(); return jsonify({"msg": "only active offers can be accepted"}), 400
    cur.execute("UPDATE applications SET status = 'Placed', remarks = 'Offer accepted by student' WHERE id = ?", (aid,))
    conn.commit(); conn.close()
    return jsonify({"msg": "offer accepted"})

if __name__ == '__main__':
    app.run(debug=True)