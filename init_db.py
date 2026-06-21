import sqlite3

def init_db():
    conn = sqlite3.connect('placement_portal.sqlite3')
    cur = conn.cursor()

    # table creation
    with open('schema.sql', 'r') as f:
        cur.executescript(f.read())

    # check admin
    cur.execute("SELECT * FROM users WHERE role = 'Admin'")
    admin_exists = cur.fetchone()

    # insert admin
    if not admin_exists:
        cur.execute('''
            INSERT INTO users (email, password, role, is_active)
            VALUES (?, ?, ?, ?)
        ''', ('admin@institute.edu', 'admin_secure_password', 'Admin', 1))
        
        conn.commit()
        print("db created")
    else:
        print("db exists")

    conn.close()

if __name__ == '__main__':
    init_db()