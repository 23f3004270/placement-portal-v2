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

# --- template routes ---
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


# --- authentication api ---
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


# --- admin api ---
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
    elif action == 'deactivate':
        cur.execute("SELECT user_id FROM companies WHERE id = ?", (cid,))
        uid = cur.fetchone()['user_id']
        cur.execute("UPDATE users SET is_active = 0 WHERE id = ?", (uid,))
        
    conn.commit()
    conn.close()
    return jsonify({"msg": "success"})


# --- company api ---
@app.route('/api/company/data', methods=['GET'])
@jwt_required()
def company_data():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT id, is_approved FROM companies WHERE user_id = ?", (get_jwt_identity(),))
    comp = cur.fetchone()
    
    if not comp or not comp['is_approved']:
        conn.close()
        return jsonify({"is_approved": False})
        
    cur.execute("SELECT * FROM job_positions WHERE company_id = ?", (comp['id'],))
    jobs = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify({"is_approved": True, "jobs": jobs, "company_id": comp['id']})

@app.route('/api/company/jobs', methods=['POST'])
@jwt_required()
def company_post_job():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO job_positions (company_id, title, description, salary, skills_required, status)
        VALUES (?, ?, ?, ?, ?, 'Active')
    """, (data['company_id'], data['title'], data['description'], data['salary'], data['skills_required']))
    
    conn.commit()
    conn.close()
    return jsonify({"msg": "posted"})

@app.route('/api/company/jobs/<int:jid>/applicants', methods=['GET'])
@jwt_required()
def company_applicants(jid):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT a.id as app_id, a.status, s.name, s.skills FROM applications a
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
    
    cur.execute("UPDATE applications SET status = ? WHERE id = ?", (data['status'], aid))
    conn.commit()
    conn.close()
    return jsonify({"msg": "updated"})


# --- student api ---
@app.route('/api/student/profile', methods=['GET', 'PUT'])
@jwt_required()
def student_profile():
    conn = get_db()
    cur = conn.cursor()
    uid = get_jwt_identity()
    
    if request.method == 'GET':
        cur.execute("SELECT * FROM students WHERE user_id = ?", (uid,))
        res = dict(cur.fetchone())
        conn.close()
        return jsonify(res)
        
    data = request.get_json()
    cur.execute("""
        UPDATE students SET name=?, education=?, cgpa=?, skills=?, resume_link=? WHERE user_id=?
    """, (data['name'], data['education'], data['cgpa'], data['skills'], data['resume_link'], uid))
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
        WHERE j.status = 'Active' AND (j.title LIKE ? OR c.name LIKE ?)
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
    
    cur.execute("SELECT id FROM students WHERE user_id = ?", (get_jwt_identity(),))
    sid = cur.fetchone()['id']
    
    try:
        cur.execute("INSERT INTO applications (student_id, job_id) VALUES (?, ?)", (sid, data['job_id']))
        conn.commit()
        ret = jsonify({"msg": "applied"}), 201
    except sqlite3.IntegrityError:
        ret = jsonify({"msg": "already applied"}), 400
        
    conn.close()
    return ret

@app.route('/api/student/applications', methods=['GET'])
@jwt_required()
def student_applications():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM students WHERE user_id = ?", (get_jwt_identity(),))
    sid = cur.fetchone()['id']
    
    cur.execute("""
        SELECT a.*, j.title, c.name as company_name FROM applications a
        JOIN job_positions j ON a.job_id = j.id
        JOIN companies c ON j.company_id = c.id WHERE a.student_id = ?
    """, (sid,))
    res = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(res)

if __name__ == '__main__':
    app.run(debug=True)