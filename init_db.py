import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('placement_portal.sqlite3')
cur = conn.cursor()

with open('schema.sql', 'r') as f:
    conn.executescript(f.read())

cur.execute("SELECT id FROM users WHERE email = 'admin@institute.edu'")
if not cur.fetchone():
    hashed_pw = generate_password_hash('admin_secure_password')
    cur.execute("INSERT INTO users (email, password, role) VALUES (?, ?, 'Admin')", ('admin@institute.edu', hashed_pw))

conn.commit()
conn.close()
print("DB initialized")