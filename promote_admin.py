import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "neurosupport.db")

def promote_user():
    email = input("Enter the email address of the user you want to make admin: ").strip()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if user exists
    cursor.execute("SELECT user_id, name, email FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    
    if not user:
        print(f"❌ User with email '{email}' not found. Please sign up first.")
        return
    
    # Promote to admin
    cursor.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (email,))
    conn.commit()
    print(f"✅ User '{email}' is now an admin!")
    
    conn.close()

if __name__ == "__main__":
    promote_user()