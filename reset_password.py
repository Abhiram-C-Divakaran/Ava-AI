import sqlite3
import hashlib
import secrets
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "neurosupport.db")

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return digest.hex(), salt

def reset_password():
    email = input("Enter your email: ").strip()
    new_password = input("Enter new password (min 6 chars): ").strip()
    
    if len(new_password) < 6:
        print("❌ Password must be at least 6 characters.")
        return
    
    password_hash, salt = hash_password(new_password)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("UPDATE users SET password_hash = ?, password_salt = ? WHERE email = ?",
                   (password_hash, salt, email))
    if cursor.rowcount == 0:
        print("❌ User not found.")
    else:
        conn.commit()
        print("✅ Password updated successfully!")
    conn.close()

if __name__ == "__main__":
    reset_password()