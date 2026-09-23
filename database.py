import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "bank.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return key.hex(), salt

def verify_password(stored_hash: str, salt: str, provided_password: str) -> bool:
    key = hashlib.pbkdf2_hmac(
        'sha256',
        provided_password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return key.hex() == stored_hash

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # Accounts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        account_number TEXT UNIQUE NOT NULL,
        account_type TEXT NOT NULL DEFAULT 'Savings' CHECK(account_type IN ('Savings', 'Checking', 'Business')),
        balance REAL NOT NULL DEFAULT 0.0,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'frozen')),
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # Transactions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference_id TEXT UNIQUE NOT NULL,
        from_account_id INTEGER,
        to_account_id INTEGER,
        transaction_type TEXT NOT NULL CHECK(transaction_type IN ('deposit', 'withdrawal', 'transfer')),
        amount REAL NOT NULL,
        description TEXT,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (from_account_id) REFERENCES accounts (id),
        FOREIGN KEY (to_account_id) REFERENCES accounts (id)
    )
    """)

    # Bank Information Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bank_info (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        bank_name TEXT NOT NULL,
        branch_name TEXT NOT NULL,
        ifsc_code TEXT NOT NULL,
        swift_code TEXT NOT NULL,
        routing_number TEXT NOT NULL,
        support_email TEXT NOT NULL,
        support_phone TEXT NOT NULL,
        address TEXT NOT NULL,
        currency_symbol TEXT NOT NULL DEFAULT '₹',
        reserve_ratio REAL NOT NULL DEFAULT 12.5,
        updated_at TEXT NOT NULL
    )
    """)

    # Active Auth Tokens
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    conn.commit()

    now_iso = datetime.now(timezone.utc).isoformat()

    # Seed Bank Info if empty
    cursor.execute("SELECT COUNT(*) FROM bank_info WHERE id = 1")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO bank_info (
            id, bank_name, branch_name, ifsc_code, swift_code, routing_number,
            support_email, support_phone, address, currency_symbol, reserve_ratio, updated_at
        ) VALUES (
            1, 'Apex Global Trust Bank', 'BKC Financial Hub Branch, Mumbai', 'APEX0008492', 'APEXINBBMUM', '400021084',
            'support@apextrust.in', '+91 (022) 5550-APEX', 'Bandra Kurla Complex, G Block, Bandra East, Mumbai, Maharashtra 400051', '₹', 15.0, ?
        )
        """, (now_iso,))
    else:
        cursor.execute("""
            UPDATE bank_info SET 
                currency_symbol = '₹',
                branch_name = 'BKC Financial Hub Branch, Mumbai',
                swift_code = 'APEXINBBMUM',
                routing_number = '400021084',
                support_email = 'support@apextrust.in',
                support_phone = '+91 (022) 5550-APEX',
                address = 'Bandra Kurla Complex, G Block, Bandra East, Mumbai, Maharashtra 400051'
            WHERE id = 1
        """)
        conn.commit()

    # Seed Admin User if not exists
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        pwd_hash, salt = hash_password("admin123")
        cursor.execute("""
        INSERT INTO users (username, password_hash, salt, role, full_name, email, phone, created_at)
        VALUES ('admin', ?, ?, 'admin', 'Alexander Vance (Chief Administrator)', 'admin@apextrust.com', '+1 (800) 555-0100', ?)
        """, (pwd_hash, salt, now_iso))

    # Seed Demo Customers if not exists
    demo_users = [
        ("john_doe", "user123", "Johnathan Doe", "john.doe@example.com", "+1 (555) 234-5678", "ACC-78401928", "Savings", 14850.75),
        ("sarah_smith", "user123", "Sarah M. Smith", "sarah.smith@example.com", "+1 (555) 876-5432", "ACC-91204851", "Checking", 32400.00),
        ("michael_chang", "user123", "Michael Chang", "m.chang@example.com", "+1 (555) 345-9876", "ACC-44910283", "Business", 68920.50),
    ]

    for username, pwd, name, email, phone, acc_no, acc_type, initial_bal in demo_users:
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            pwd_hash, salt = hash_password(pwd)
            cursor.execute("""
            INSERT INTO users (username, password_hash, salt, role, full_name, email, phone, created_at)
            VALUES (?, ?, ?, 'user', ?, ?, ?, ?)
            """, (username, pwd_hash, salt, name, email, phone, now_iso))
            user_id = cursor.lastrowid

            cursor.execute("""
            INSERT INTO accounts (user_id, account_number, account_type, balance, status, created_at)
            VALUES (?, ?, ?, ?, 'active', ?)
            """, (user_id, acc_no, acc_type, initial_bal, now_iso))
            acc_id = cursor.lastrowid

            # Add initial deposit transaction
            ref = "TXN-" + secrets.token_hex(4).upper()
            t_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
            cursor.execute("""
            INSERT INTO transactions (reference_id, from_account_id, to_account_id, transaction_type, amount, description, timestamp)
            VALUES (?, NULL, ?, 'deposit', ?, 'Initial Account Opening Deposit', ?)
            """, (ref, acc_id, initial_bal, t_time))

    # Add sample transactions if few exist
    cursor.execute("SELECT COUNT(*) FROM transactions")
    if cursor.fetchone()[0] <= 3:
        cursor.execute("SELECT id FROM accounts WHERE account_number = 'ACC-78401928'")
        john_acc = cursor.fetchone()
        cursor.execute("SELECT id FROM accounts WHERE account_number = 'ACC-91204851'")
        sarah_acc = cursor.fetchone()

        if john_acc and sarah_acc:
            ref1 = "TXN-" + secrets.token_hex(4).upper()
            cursor.execute("""
            INSERT INTO transactions (reference_id, from_account_id, to_account_id, transaction_type, amount, description, timestamp)
            VALUES (?, ?, ?, 'transfer', 500.0, 'Consulting invoice payment', ?)
            """, (ref1, john_acc[0], sarah_acc[0], (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()))

            ref2 = "TXN-" + secrets.token_hex(4).upper()
            cursor.execute("""
            INSERT INTO transactions (reference_id, from_account_id, to_account_id, transaction_type, amount, description, timestamp)
            VALUES (?, ?, NULL, 'withdrawal', 200.0, 'ATM Cash Withdrawal - Midtown', ?)
            """, (ref2, john_acc[0], (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database schema checked and initialized.")
