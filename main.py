import os
import secrets
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import get_db, init_db, verify_password, hash_password
from auth import create_session, delete_session, get_current_user, get_admin_user

app = FastAPI(
    title="Apex Global Trust Bank Management System",
    description="Full-featured banking system with Admin & User portals, bank parameters, and transactions.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database schema and default records
init_db()

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
os.makedirs(os.path.join(static_dir, "css"), exist_ok=True)
os.makedirs(os.path.join(static_dir, "js"), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), "templates"), exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ----------------- Pydantic Models -----------------

class LoginRequest(BaseModel):
    username: str
    password: str

class BankInfoUpdateRequest(BaseModel):
    bank_name: str
    branch_name: str
    ifsc_code: str
    swift_code: str
    routing_number: str
    support_email: str
    support_phone: str
    address: str
    reserve_ratio: float = 12.5

class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to deposit, must be positive")
    description: Optional[str] = "Cash Deposit"

class WithdrawRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to withdraw, must be positive")
    description: Optional[str] = "Cash Withdrawal"

class TransferRequest(BaseModel):
    to_account_number: str
    amount: float = Field(..., gt=0, description="Amount to transfer, must be positive")
    description: Optional[str] = "Funds Transfer"

class CreateCustomerRequest(BaseModel):
    username: str
    password: str
    full_name: str
    email: str
    phone: str
    account_type: str = "Savings"
    initial_deposit: float = Field(0.0, ge=0)

class AccountStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|frozen)$")

# ----------------- Auth Endpoints -----------------

@app.post("/api/auth/login")
def login(creds: LoginRequest, response: Response):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash, salt, role, full_name, email FROM users WHERE username = ?", (creds.username,))
    user = cursor.fetchone()
    conn.close()

    if not user or not verify_password(user["password_hash"], user["salt"], creds.password):
        raise HTTPException(status_code=400, detail="Invalid username or password")

    token = create_session(user["id"])
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "full_name": user["full_name"],
            "email": user["email"]
        }
    }

@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    if not token:
        token = request.cookies.get("session_token")
    
    if token:
        delete_session(token)
    response.delete_cookie(key="session_token")
    return {"message": "Logged out successfully"}

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"user": user}

# ----------------- Bank Info Endpoints -----------------

@app.get("/api/bank/info")
def get_bank_info():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bank_info WHERE id = 1")
    info = cursor.fetchone()
    conn.close()
    if not info:
        raise HTTPException(status_code=404, detail="Bank information not found")
    return dict(info)

@app.put("/api/bank/info")
def update_bank_info(payload: BankInfoUpdateRequest, admin: dict = Depends(get_admin_user)):
    conn = get_db()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        UPDATE bank_info SET
            bank_name = ?, branch_name = ?, ifsc_code = ?, swift_code = ?,
            routing_number = ?, support_email = ?, support_phone = ?,
            address = ?, reserve_ratio = ?, updated_at = ?
        WHERE id = 1
    """, (
        payload.bank_name, payload.branch_name, payload.ifsc_code, payload.swift_code,
        payload.routing_number, payload.support_email, payload.support_phone,
        payload.address, payload.reserve_ratio, now_iso
    ))
    conn.commit()
    conn.close()
    return {"message": "Bank details updated successfully"}

# ----------------- Admin Endpoints -----------------

@app.get("/api/admin/metrics")
def get_admin_metrics(admin: dict = Depends(get_admin_user)):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM accounts")
    total_accounts = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM accounts WHERE status = 'active'")
    active_accounts = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(balance), 0) FROM accounts")
    total_vault_deposits = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM transactions")
    total_transactions = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions")
    total_volume = cursor.fetchone()[0]

    conn.close()
    return {
        "total_accounts": total_accounts,
        "active_accounts": active_accounts,
        "frozen_accounts": total_accounts - active_accounts,
        "total_vault_deposits": round(total_vault_deposits, 2),
        "total_transactions": total_transactions,
        "total_volume": round(total_volume, 2),
    }

@app.get("/api/admin/accounts")
def list_admin_accounts(admin: dict = Depends(get_admin_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.account_number, a.account_type, a.balance, a.status, a.created_at,
               u.id as user_id, u.username, u.full_name, u.email, u.phone
        FROM accounts a
        JOIN users u ON a.user_id = u.id
        ORDER BY a.id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/admin/accounts")
def create_customer_account(payload: CreateCustomerRequest, admin: dict = Depends(get_admin_user)):
    conn = get_db()
    cursor = conn.cursor()

    # Check if username or email already exists
    cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", (payload.username, payload.email))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username or Email already registered")

    now_iso = datetime.now(timezone.utc).isoformat()
    pwd_hash, salt = hash_password(payload.password)

    try:
        # Create user
        cursor.execute("""
            INSERT INTO users (username, password_hash, salt, role, full_name, email, phone, created_at)
            VALUES (?, ?, ?, 'user', ?, ?, ?, ?)
        """, (payload.username, pwd_hash, salt, payload.full_name, payload.email, payload.phone, now_iso))
        user_id = cursor.lastrowid

        # Generate unique account number
        acc_num = f"ACC-{secrets.randbelow(90000000) + 10000000}"

        # Create account
        cursor.execute("""
            INSERT INTO accounts (user_id, account_number, account_type, balance, status, created_at)
            VALUES (?, ?, ?, ?, 'active', ?)
        """, (user_id, acc_num, payload.account_type, payload.initial_deposit, now_iso))
        acc_id = cursor.lastrowid

        # If initial deposit > 0, log transaction
        if payload.initial_deposit > 0:
            ref = "TXN-" + secrets.token_hex(4).upper()
            cursor.execute("""
                INSERT INTO transactions (reference_id, from_account_id, to_account_id, transaction_type, amount, description, timestamp)
                VALUES (?, NULL, ?, 'deposit', ?, 'Initial Account Opening Deposit', ?)
            """, (ref, acc_id, payload.initial_deposit, now_iso))

        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    conn.close()
    return {"message": "Customer account created successfully", "account_number": acc_num}

@app.patch("/api/admin/accounts/{account_number}/status")
def toggle_account_status(account_number: str, payload: AccountStatusUpdate, admin: dict = Depends(get_admin_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, status FROM accounts WHERE account_number = ?", (account_number,))
    acc = cursor.fetchone()
    if not acc:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")

    cursor.execute("UPDATE accounts SET status = ? WHERE account_number = ?", (payload.status, account_number))
    conn.commit()
    conn.close()
    return {"message": f"Account status updated to {payload.status}"}

@app.get("/api/admin/transactions")
def list_all_transactions(admin: dict = Depends(get_admin_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.reference_id, t.transaction_type, t.amount, t.description, t.timestamp,
               t.from_account_id, t.to_account_id,
               fa.account_number as from_account_number, fu.full_name as from_user_name,
               ta.account_number as to_account_number, tu.full_name as to_user_name
        FROM transactions t
        LEFT JOIN accounts fa ON t.from_account_id = fa.id
        LEFT JOIN users fu ON fa.user_id = fu.id
        LEFT JOIN accounts ta ON t.to_account_id = ta.id
        LEFT JOIN users tu ON ta.user_id = tu.id
        ORDER BY t.id DESC
        LIMIT 200
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ----------------- User / Customer Endpoints -----------------

@app.get("/api/user/account")
def get_user_account(user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.account_number, a.account_type, a.balance, a.status, a.created_at,
               b.bank_name, b.branch_name, b.ifsc_code, b.swift_code
        FROM accounts a
        CROSS JOIN bank_info b
        WHERE a.user_id = ? AND b.id = 1
    """, (user["id"],))
    account = cursor.fetchone()
    conn.close()

    if not account:
        raise HTTPException(status_code=404, detail="No active bank account associated with this profile")

    # Generate deterministic card presentation details based on account number
    acc_clean = account["account_number"].replace("ACC-", "")
    card_number = f"4892 {acc_clean[:4]} {acc_clean[4:8]} 9012"

    return {
        **dict(account),
        "user_full_name": user["full_name"],
        "user_email": user["email"],
        "user_phone": user.get("phone", "N/A"),
        "card_number": card_number,
        "card_expiry": "11/29",
        "card_type": "Apex Platinum Debit"
    }

@app.get("/api/user/lookup-account/{account_number}")
def lookup_account(account_number: str, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.account_number, a.status, u.full_name
        FROM accounts a
        JOIN users u ON a.user_id = u.id
        WHERE a.account_number = ?
    """, (account_number.strip(),))
    dest = cursor.fetchone()
    conn.close()

    if not dest:
        raise HTTPException(status_code=404, detail="Destination account does not exist")
    if dest["status"] != "active":
        raise HTTPException(status_code=400, detail="Destination account is currently frozen or inactive")

    return {
        "account_number": dest["account_number"],
        "recipient_name": dest["full_name"],
        "status": dest["status"]
    }

@app.post("/api/user/deposit")
def user_deposit(payload: DepositRequest, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, balance, status FROM accounts WHERE user_id = ?", (user["id"],))
    acc = cursor.fetchone()

    if not acc:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")
    if acc["status"] != "active":
        conn.close()
        raise HTTPException(status_code=403, detail="Account is frozen. Contact administrator.")

    new_balance = round(acc["balance"] + payload.amount, 2)
    ref = "TXN-" + secrets.token_hex(4).upper()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        cursor.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_balance, acc["id"]))
        cursor.execute("""
            INSERT INTO transactions (reference_id, from_account_id, to_account_id, transaction_type, amount, description, timestamp)
            VALUES (?, NULL, ?, 'deposit', ?, ?, ?)
        """, (ref, acc["id"], payload.amount, payload.description or "Online Deposit", now_iso))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    conn.close()
    return {
        "message": f"Successfully deposited ₹{payload.amount:,.2f}",
        "reference_id": ref,
        "new_balance": new_balance
    }

@app.post("/api/user/withdraw")
def user_withdraw(payload: WithdrawRequest, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, balance, status FROM accounts WHERE user_id = ?", (user["id"],))
    acc = cursor.fetchone()

    if not acc:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")
    if acc["status"] != "active":
        conn.close()
        raise HTTPException(status_code=403, detail="Account is frozen. Withdrawals suspended.")
    if acc["balance"] < payload.amount:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Insufficient balance. Current balance: ₹{acc['balance']:,.2f}")

    new_balance = round(acc["balance"] - payload.amount, 2)
    ref = "TXN-" + secrets.token_hex(4).upper()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        cursor.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_balance, acc["id"]))
        cursor.execute("""
            INSERT INTO transactions (reference_id, from_account_id, to_account_id, transaction_type, amount, description, timestamp)
            VALUES (?, ?, NULL, 'withdrawal', ?, ?, ?)
        """, (ref, acc["id"], payload.amount, payload.description or "ATM/Online Withdrawal", now_iso))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    conn.close()
    return {
        "message": f"Successfully withdrawn ₹{payload.amount:,.2f}",
        "reference_id": ref,
        "new_balance": new_balance
    }

@app.post("/api/user/transfer")
def user_transfer(payload: TransferRequest, user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, account_number, balance, status FROM accounts WHERE user_id = ?", (user["id"],))
    src = cursor.fetchone()

    if not src:
        conn.close()
        raise HTTPException(status_code=404, detail="Sender account not found")
    if src["status"] != "active":
        conn.close()
        raise HTTPException(status_code=403, detail="Your account is frozen. Transfers are prohibited.")

    target_acc_num = payload.to_account_number.strip()
    if target_acc_num == src["account_number"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot transfer funds to the same account")

    cursor.execute("SELECT id, balance, status FROM accounts WHERE account_number = ?", (target_acc_num,))
    dest = cursor.fetchone()

    if not dest:
        conn.close()
        raise HTTPException(status_code=404, detail="Destination account not found")
    if dest["status"] != "active":
        conn.close()
        raise HTTPException(status_code=400, detail="Destination account is inactive or frozen")

    if src["balance"] < payload.amount:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Insufficient balance. Current balance: ₹{src['balance']:,.2f}")

    new_src_balance = round(src["balance"] - payload.amount, 2)
    new_dest_balance = round(dest["balance"] + payload.amount, 2)
    ref = "TXN-" + secrets.token_hex(4).upper()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        cursor.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_src_balance, src["id"]))
        cursor.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_dest_balance, dest["id"]))
        cursor.execute("""
            INSERT INTO transactions (reference_id, from_account_id, to_account_id, transaction_type, amount, description, timestamp)
            VALUES (?, ?, ?, 'transfer', ?, ?, ?)
        """, (ref, src["id"], dest["id"], payload.amount, payload.description or "Peer Transfer", now_iso))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    conn.close()
    return {
        "message": f"Successfully transferred ₹{payload.amount:,.2f} to {target_acc_num}",
        "reference_id": ref,
        "new_balance": new_src_balance
    }

@app.get("/api/user/transactions")
def get_user_transactions(user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM accounts WHERE user_id = ?", (user["id"],))
    acc = cursor.fetchone()
    if not acc:
        conn.close()
        return []

    acc_id = acc["id"]
    cursor.execute("""
        SELECT t.id, t.reference_id, t.transaction_type, t.amount, t.description, t.timestamp,
               t.from_account_id, t.to_account_id,
               fa.account_number as from_account_number, fu.full_name as from_user_name,
               ta.account_number as to_account_number, tu.full_name as to_user_name
        FROM transactions t
        LEFT JOIN accounts fa ON t.from_account_id = fa.id
        LEFT JOIN users fu ON fa.user_id = fu.id
        LEFT JOIN accounts ta ON t.to_account_id = ta.id
        LEFT JOIN users tu ON ta.user_id = tu.id
        WHERE t.from_account_id = ? OR t.to_account_id = ?
        ORDER BY t.id DESC
        LIMIT 100
    """, (acc_id, acc_id))

    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        # Determine if it's credit or debit for this user
        if d["transaction_type"] == "deposit" or d["to_account_id"] == acc_id:
            d["flow"] = "credit"
        else:
            d["flow"] = "debit"
        result.append(d)

    return result

# ----------------- Frontend HTML Root -----------------

@app.get("/", response_class=HTMLResponse)
def index_view():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
