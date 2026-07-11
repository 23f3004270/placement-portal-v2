import sqlite3
from flask import Flask, render_template, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt, get_jwt_identity
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = 'super-secret-key'
jwt = JWTManager(app)

def get_db():
    conn = sqlite3.connect('placement_portal.sqlite3')
    conn.row_factory = sqlite3.Row
    return conn

# template routes
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/company')
def company_page():
    return render_template('company.html')

@app.route('/student')
def student_page():
    return render_template('student.html')


# auth api
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (data['email'],))
    user = cur.fetchone()
    conn.close()
    
    if user and check_password_hash(user['password'], data['password']):
        if not user['is_active']:
            return jsonify({"msg": "account deactivated"}), 403
        token = create_access_token(identity=str(user['id']), additional_claims={"role": user['role']})
        return jsonify({"token": token, "role": user['role']})
    return jsonify({"msg": "invalid credentials"}), 401

@app.route('/api/register/student', methods=['POST'])
def reg_student():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    try:
        hashed_pw = generate_password_hash(data['password'])
        cur.execute("INSERT INTO users (email, password, role) VALUES (?, ?, 'Student')", (data['email'], hashed_pw))
        user_id = cur.lastrowid
        cur.execute("INSERT INTO students (user_id, name) VALUES (?, ?)", (user_id, data['name']))
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"msg": "email exists"}), 400
    finally:
        conn.close()
    return jsonify({"msg": "registered"}), 201

@app.route('/api/register/company', methods=['POST'])
def reg_company():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    try:
        hashed_pw = generate_password_hash(data['password'])
        cur.execute("INSERT INTO users (email, password, role) VALUES (?, ?, 'Company')", (data['email'], hashed_pw))
        user_id = cur.lastrowid
        cur.execute("INSERT INTO companies (user_id, name) VALUES (?, ?)", (user_id, data['name']))
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"msg": "email exists"}), 400
    finally:
        conn.close()
    return jsonify({"msg": "registered"}), 201


# admin api
@app.route('/api/admin/stats', methods=['GET'])
@jwt_required()
def admin_stats():
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM students")
    s_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM companies")
    c_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM job_positions")
    j_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM applications")
    a_count = cur.fetchone()[0]
    conn.close()
    return jsonify({"students": s_count, "companies": c_count, "jobs": j_count, "applications": a_count})

@app.route('/api/admin/companies', methods=['GET'])
@jwt_required()
def admin_companies():
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    search = request.args.get('search', '')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.*, u.is_active FROM companies c 
        JOIN users u ON c.user_id = u.id 
        WHERE c.name LIKE ?
    """, (f'%{search}%',))
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/admin/companies/<int:cid>/<action>', methods=['POST'])
@jwt_required()
def admin_manage_company(cid, action):
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    conn = get_db()
    cur = conn.cursor()
    
    if action == 'approve':
        cur.execute("UPDATE companies SET is_approved = 1 WHERE id = ?", (cid,))
    elif action == 'reject':
        cur.execute("UPDATE companies SET is_approved = 0 WHERE id = ?", (cid,))
    elif action == 'deactivate':
        cur.execute("SELECT user_id FROM companies WHERE id = ?", (cid,))
        uid = cur.fetchone()['user_id']
        cur.execute("UPDATE users SET is_active = 0 WHERE id = ?", (uid,))
    elif action == 'activate':
        cur.execute("SELECT user_id FROM companies WHERE id = ?", (cid,))
        uid = cur.fetchone()['user_id']
        cur.execute("UPDATE users SET is_active = 1 WHERE id = ?", (uid,))
    elif action == 'delete':
        cur.execute("SELECT user_id FROM companies WHERE id = ?", (cid,))
        row = cur.fetchone()
        if row:
            uid = row['user_id']
            cur.execute("DELETE FROM applications WHERE job_id IN (SELECT id FROM job_positions WHERE company_id = ?)", (cid,))
            cur.execute("DELETE FROM job_positions WHERE company_id = ?", (cid,))
            cur.execute("DELETE FROM companies WHERE id = ?", (cid,))
            cur.execute("DELETE FROM users WHERE id = ?", (uid,))
            
    conn.commit()
    conn.close()
    return jsonify({"msg": "success"})

@app.route('/api/admin/students', methods=['GET'])
@jwt_required()
def admin_students():
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    search = request.args.get('search', '')
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT s.*, 
               (s.ug_degree || ' (' || s.ug_specialization || ')') AS education,
               u.is_active FROM students s
        JOIN users u ON s.user_id = u.id
        WHERE s.name LIKE ? OR s.skills LIKE ?
    """, (f'%{search}%', f'%{search}%'))
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/admin/students/<int:sid>/<action>', methods=['POST'])
@jwt_required()
def admin_manage_student(sid, action):
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM students WHERE id = ?", (sid,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"msg": "student not found"}), 404
        
    uid = row['user_id']
    if action == 'deactivate':
        cur.execute("UPDATE users SET is_active = 0 WHERE id = ?", (uid,))
    elif action == 'activate':
        cur.execute("UPDATE users SET is_active = 1 WHERE id = ?", (uid,))
    elif action == 'delete':
        cur.execute("DELETE FROM applications WHERE student_id = ?", (sid,))
        cur.execute("DELETE FROM students WHERE id = ?", (sid,))
        cur.execute("DELETE FROM users WHERE id = ?", (uid,))
        
    conn.commit()
    conn.close()
    return jsonify({"msg": "success"})

@app.route('/api/admin/jobs', methods=['GET'])
@jwt_required()
def admin_jobs():
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT j.*, c.name as company_name FROM job_positions j
        JOIN companies c ON j.company_id = c.id
    """)
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/admin/jobs/<int:jid>/<action>', methods=['POST'])
@jwt_required()
def admin_manage_job(jid, action):
    if get_jwt().get('role') != 'Admin': return jsonify({"msg": "forbidden"}), 403
    conn = get_db()
    cur = conn.cursor()
    if action == 'approve':
        cur.execute("UPDATE job_positions SET status = 'Active' WHERE id = ?", (jid,))
    elif action == 'reject':
        cur.execute("UPDATE job_positions SET status = 'Rejected' WHERE id = ?", (jid,))
    conn.commit()
    conn.close()
    return jsonify({"msg": "success"})


# company api
@app.route('/api/company/data', methods=['GET'])
@jwt_required()
def company_data():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, is_approved FROM companies WHERE user_id = ?", (int(get_jwt_identity()),))
    comp = cur.fetchone()
    if not comp or not comp['is_approved']:
        conn.close()
        return jsonify({"is_approved": False})
        
    cur.execute("SELECT * FROM job_positions WHERE company_id = ?", (comp['id'],))
    jobs = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify({"is_approved": True, "name": comp['name'], "jobs": jobs, "company_id": comp['id']})

@app.route('/api/company/jobs', methods=['POST'])
@jwt_required()
def company_post_job():
    data = request.get_json()
    title = data.get('title', '').strip()
    
    if not title or title.isdigit():
        return jsonify({"msg": "job title cannot be numeric only or empty"}), 400
        
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_approved FROM companies WHERE id = ?", (data['company_id'],))
    comp = cur.fetchone()
    if not comp or not comp['is_approved']:
        conn.close()
        return jsonify({"msg": "company profile not approved"}), 403
        
    cur.execute("""
        INSERT INTO job_positions (company_id, title, description, salary, skills_required, status)
        VALUES (?, ?, ?, ?, ?, 'Pending')
    """, (data['company_id'], title, data['description'], int(data['salary']), data['skills_required']))
    conn.commit()
    conn.close()
    return jsonify({"msg": "posted"})

@app.route('/api/company/jobs/<int:jid>/applicants', methods=['GET'])
@jwt_required()
def company_applicants(jid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.id as app_id, a.status, a.remarks, s.name, s.skills, s.resume_link, 
               s.ug_degree, s.ug_specialization, s.pg_degree, s.pg_specialization, s.cgpa
        FROM applications a
        JOIN students s ON a.student_id = s.id WHERE a.job_id = ?
    """, (jid,))
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

@app.route('/api/company/applications/<int:aid>/status', methods=['PUT'])
@jwt_required()
def company_update_status(aid):
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    remarks = data.get('remarks', '')
    cur.execute("UPDATE applications SET status = ?, remarks = ? WHERE id = ?", (data['status'], remarks, aid))
    conn.commit()
    conn.close()
    return jsonify({"msg": "updated"})


# student api
@app.route('/api/student/profile', methods=['GET', 'PUT'])
@jwt_required()
def student_profile():
    conn = get_db()
    cur = conn.cursor()
    uid = int(get_jwt_identity())
    
    if request.method == 'GET':
        cur.execute("SELECT * FROM students WHERE user_id = ?", (uid,))
        res = dict(cur.fetchone())
        conn.close()
        return jsonify(res)
        
    data = request.get_json()
    if not all([data.get('name'), data.get('ug_degree'), data.get('ug_specialization'), data.get('cgpa'), data.get('skills'), data.get('resume_link')]):
        return jsonify({"msg": "all required profile fields must be completed"}), 400

    cur.execute("""
        UPDATE students SET name=?, ug_degree=?, ug_specialization=?, pg_degree=?, pg_specialization=?, cgpa=?, skills=?, resume_link=? WHERE user_id=?
    """, (data['name'], data['ug_degree'], data['ug_specialization'], data.get('pg_degree'), data.get('pg_specialization'), float(data['cgpa']), data['skills'], data['resume_link'], uid))
    conn.commit()
    conn.close()
    return jsonify({"msg": "updated"})

@app.route('/api/student/jobs', methods=['GET'])
@jwt_required()
def student_jobs():
    search = request.args.get('search', '')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT j.*, c.name as company_name FROM job_positions j
        JOIN companies c ON j.company_id = c.id
        WHERE j.status = 'Active' AND c.is_approved = 1 AND (j.title LIKE ? OR c.name LIKE ?)
    """, (f'%{search}%', f'%{search}%'))
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
    student = cur.fetchone()
    sid = student['id']
    
    if not all([student['name'], student['ug_degree'], student['ug_specialization'], student['cgpa'], student['skills'], student['resume_link']]):
        conn.close()
        return jsonify({"msg": "complete your profile details before applying"}), 400
        
    cur.execute("SELECT id FROM applications WHERE student_id = ? AND job_id = ?", (sid, data['job_id']))
    if cur.fetchone():
        conn.close()
        return jsonify({"msg": "already applied to this job"}), 400
        
    cur.execute("INSERT INTO applications (student_id, job_id, status) VALUES (?, ?, 'Applied')", (sid, data['job_id']))
    conn.commit()
    conn.close()
    return jsonify({"msg": "applied"}), 201

@app.route('/api/student/applications', methods=['GET'])
@jwt_required()
def student_applications():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM students WHERE user_id = ?", (int(get_jwt_identity()),))
    sid = cur.fetchone()['id']
    
    cur.execute("""
        SELECT a.*, j.title, j.skills_required, c.name as company_name FROM applications a
        JOIN job_positions j ON a.job_id = j.id
        JOIN companies c ON j.company_id = c.id WHERE a.student_id = ?
    """, (sid,))
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
    
    if not student:
        conn.close()
        return jsonify({"msg": "student not found"}), 404
        
    cur.execute("SELECT status FROM applications WHERE id = ? AND student_id = ?", (aid, student['id']))
    app_row = cur.fetchone()
    if not app_row:
        conn.close()
        return jsonify({"msg": "application record not found"}), 404
        
    if app_row['status'] != 'Offer':
        conn.close()
        return jsonify({"msg": "only active offers can be accepted"}), 400
        
    cur.execute("UPDATE applications SET status = 'Placed', remarks = 'Offer accepted by student' WHERE id = ?", (aid,))
    conn.commit()
    conn.close()
    return jsonify({"msg": "offer accepted"})

if __name__ == '__main__':
    app.run(debug=True)