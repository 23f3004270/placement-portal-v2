import sqlite3
from werkzeug.security import generate_password_hash

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    industry TEXT,
    location TEXT,
    description TEXT,
    is_approved BOOLEAN DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    ug_degree TEXT,
    ug_specialization TEXT,
    pg_degree TEXT,
    pg_specialization TEXT,
    cgpa REAL,
    skills TEXT,
    resume_link TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS job_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    salary INTEGER,
    skills_required TEXT,
    status TEXT DEFAULT 'Pending',
    FOREIGN KEY (company_id) REFERENCES companies (id)
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    job_id INTEGER NOT NULL,
    status TEXT DEFAULT 'Applied',
    remarks TEXT DEFAULT '',
    applied_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students (id),
    FOREIGN KEY (job_id) REFERENCES job_positions (id)
);
"""

conn = sqlite3.connect('placement_portal.sqlite3')
cur = conn.cursor()

conn.executescript(SCHEMA_SQL)

cur.execute("SELECT id FROM users WHERE email = 'admin@institute.edu'")
if not cur.fetchone():
    hashed_pw = generate_password_hash('admin_secure_password')
    cur.execute("INSERT INTO users (email, password, role) VALUES (?, ?, 'Admin')", ('admin@institute.edu', hashed_pw))

conn.commit()
conn.close()
print("DB initialized")