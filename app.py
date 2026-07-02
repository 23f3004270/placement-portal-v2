from flask import Flask, request, jsonify, render_template
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
# secure key for jwt generation
app.config['JWT_SECRET_KEY'] = 'ppa-v2-super-secret-key'
jwt = JWTManager(app)

# db connection helper
def get_db():
    conn = sqlite3.connect('placement_portal.sqlite3')
    conn.row_factory = sqlite3.Row
    return conn

# serve the vue frontend
@app.route('/')
def index():
    return render_template('index.html')

# user login route
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cur.fetchone()
    conn.close()

    # check password and issue token
    if user and check_password_hash(user['password'], password):
        if not user['is_active']:
            return jsonify({"msg": "account disabled"}), 403
        
        access_token = create_access_token(
            identity=user['id'], 
            additional_claims={"role": user['role']}
        )
        return jsonify({"token": access_token, "role": user['role']}), 200

    return jsonify({"msg": "invalid credentials"}), 401

# student registration route
@app.route('/api/register/student', methods=['POST'])
def register_student():
    data = request.get_json()
    hashed_pw = generate_password_hash(data.get('password'))
    
    conn = get_db()
    cur = conn.cursor()
    try:
        # insert user
        cur.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", 
                    (data.get('email'), hashed_pw, 'Student'))
        user_id = cur.lastrowid
        
        # insert student profile
        cur.execute("INSERT INTO students (user_id, name) VALUES (?, ?)", 
                    (user_id, data.get('name')))
        conn.commit()
        return jsonify({"msg": "student registered successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"msg": "email already exists"}), 400
    finally:
        conn.close()

# company registration route
@app.route('/api/register/company', methods=['POST'])
def register_company():
    data = request.get_json()
    hashed_pw = generate_password_hash(data.get('password'))
    
    conn = get_db()
    cur = conn.cursor()
    try:
        # insert user
        cur.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", 
                    (data.get('email'), hashed_pw, 'Company'))
        user_id = cur.lastrowid
        
        # insert company profile (is_approved defaults to 0 based on schema)
        cur.execute("INSERT INTO companies (user_id, name) VALUES (?, ?)", 
                    (user_id, data.get('name')))
        conn.commit()
        return jsonify({"msg": "company registered successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"msg": "email already exists"}), 400
    finally:
        conn.close()

# admin check helper
def is_admin():
    claims = get_jwt()
    return claims.get('role') == 'Admin'

# get admin stats
@app.route('/api/admin/stats', methods=['GET'])
@jwt_required()
def admin_stats():
    if not is_admin(): 
        return jsonify({"msg": "unauthorized"}), 403
    
    conn = get_db()
    cur = conn.cursor()
    
    # fetch stats
    cur.execute("SELECT COUNT(*) FROM students")
    students_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM companies")
    companies_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM job_positions")
    jobs_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM applications")
    apps_count = cur.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        "students": students_count,
        "companies": companies_count,
        "jobs": jobs_count,
        "applications": apps_count
    })

# get and search companies
@app.route('/api/admin/companies', methods=['GET'])
@jwt_required()
def get_companies():
    if not is_admin(): 
        return jsonify({"msg": "unauthorized"}), 403
    
    search = request.args.get('search', '')
    conn = get_db()
    cur = conn.cursor()
    
    # search logic
    query = """
        SELECT c.id, c.name, c.industry, c.is_approved, u.is_active 
        FROM companies c 
        JOIN users u ON c.user_id = u.id
        WHERE c.name LIKE ? OR c.industry LIKE ?
    """
    cur.execute(query, (f'%{search}%', f'%{search}%'))
    companies = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    return jsonify(companies)

# toggle company approval
@app.route('/api/admin/companies/<int:company_id>/<action>', methods=['POST'])
@jwt_required()
def manage_company(company_id, action):
    if not is_admin(): 
        return jsonify({"msg": "unauthorized"}), 403
    
    conn = get_db()
    cur = conn.cursor()
    
    # update status
    if action == 'approve':
        cur.execute("UPDATE companies SET is_approved = 1 WHERE id = ?", (company_id,))
    elif action == 'deactivate':
        cur.execute("SELECT user_id FROM companies WHERE id = ?", (company_id,))
        user = cur.fetchone()
        if user:
            cur.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user['user_id'],))
            
    conn.commit()
    conn.close()
    return jsonify({"msg": "success"})

# get company dashboard and jobs
@app.route('/api/company/data', methods=['GET'])
@jwt_required()
def get_company_data():
    if get_jwt().get('role') != 'Company': 
        return jsonify({"msg": "unauthorized"}), 403
    
    conn = get_db()
    cur = conn.cursor()
    
    # check approval
    cur.execute("SELECT id, is_approved FROM companies WHERE user_id = ?", (get_jwt_identity(),))
    company = cur.fetchone()
    
    if not company or not company['is_approved']:
        conn.close()
        return jsonify({"is_approved": False})
        
    comp_id = company['id']
    
    # fetch company jobs
    cur.execute("SELECT * FROM job_positions WHERE company_id = ?", (comp_id,))
    jobs = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    return jsonify({"is_approved": True, "jobs": jobs, "company_id": comp_id})

# post a new job
@app.route('/api/company/jobs', methods=['POST'])
@jwt_required()
def post_job():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    
    # insert job
    cur.execute("""
        INSERT INTO job_positions (company_id, title, description, salary, skills_required, status) 
        VALUES (?, ?, ?, ?, ?, 'Active')
    """, (data['company_id'], data['title'], data['description'], data['salary'], data['skills_required']))
    
    conn.commit()
    conn.close()
    return jsonify({"msg": "job posted successfully"}), 201

# get applicants for a specific job
@app.route('/api/company/jobs/<int:job_id>/applicants', methods=['GET'])
@jwt_required()
def get_applicants(job_id):
    conn = get_db()
    cur = conn.cursor()
    
    # join applications with student profiles
    query = """
        SELECT a.id as app_id, a.status, s.name, s.education, s.skills
        FROM applications a
        JOIN students s ON a.student_id = s.id
        WHERE a.job_id = ?
    """
    cur.execute(query, (job_id,))
    applicants = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    return jsonify(applicants)

# update application status (shortlist/reject/select)
@app.route('/api/company/applications/<int:app_id>/status', methods=['PUT'])
@jwt_required()
def update_app_status(app_id):
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    
    # update status
    cur.execute("UPDATE applications SET status = ? WHERE id = ?", (data['status'], app_id))
    
    conn.commit()
    conn.close()
    return jsonify({"msg": "status updated"})

if __name__ == '__main__':
    app.run(debug=True)