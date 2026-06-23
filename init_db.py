import sqlite3
from werkzeug.security import generate_password_hash

def init_db():
    conn = sqlite3.connect('placement_portal.sqlite3')
    cur = conn.cursor()

    # table creation
    with open('schema.sql', 'r') as f:
        cur.executescript(f.read())

    # check admin
    cur.execute("SELECT * FROM users WHERE role = 'Admin'")
    admin_exists = cur.fetchone()

    # insert admin securely
    if not admin_exists:
        hashed_pw = generate_password_hash('admin_secure_password')
        cur.execute('''
            INSERT INTO users (email, password, role, is_active)
            VALUES (?, ?, ?, ?)
        ''', ('admin@institute.edu', hashed_pw, 'Admin', 1))
        
        conn.commit()
        print("db created")
    else:
        print("db exists")

    conn.close()

if __name__ == '__main__':
    init_db()