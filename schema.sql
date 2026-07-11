-- users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL, -- 'Admin', 'Company', 'Student'
    is_active BOOLEAN DEFAULT 1
);

-- companies table
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

-- students table
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    education TEXT,
    cgpa REAL,
    skills TEXT,
    resume_link TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- job positions table
CREATE TABLE IF NOT EXISTS job_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    salary TEXT,
    skills_required TEXT,
    status TEXT DEFAULT 'Pending', -- 'Pending', 'Active', 'Closed'
    FOREIGN KEY (company_id) REFERENCES companies (id)
);

-- applications table
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    job_id INTEGER NOT NULL,
    status TEXT DEFAULT 'Applied', -- 'Applied', 'Shortlisted', 'Selected', 'Rejected'
    applied_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students (id),
    FOREIGN KEY (job_id) REFERENCES job_positions (id)
);