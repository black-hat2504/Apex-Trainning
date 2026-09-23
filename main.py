import os, secrets
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from database import get_db, init_db, db_query, db_execute, verify_password, hash_password
from auth import create_session, delete_session, get_current_user, get_admin_user

app = FastAPI(title="Apex Global Trust Bank Management System")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
init_db()

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Models
class LoginReq(BaseModel): username: str; password: str
class BankInfoReq(BaseModel): bank_name: str; branch_name: str; ifsc_code: str; swift_code: str; routing_number: str; support_email: str; support_phone: str; address: str; reserve_ratio: float = 12.5
class DepositReq(BaseModel): amount: float = Field(..., gt=0); description: Optional[str] = "Cash Deposit"
class WithdrawReq(BaseModel): amount: float = Field(..., gt=0); description: Optional[str] = "Cash Withdrawal"
class TransferReq(BaseModel): to_account_number: str; amount: float = Field(..., gt=0); description: Optional[str] = "Funds Transfer"
class CreateCustomerReq(BaseModel): username: str; password: str; full_name: str; email: str; phone: str; account_type: str = "Savings"; initial_deposit: float = Field(0.0, ge=0)
class StatusReq(BaseModel): status: str = Field(..., pattern="^(active|frozen)$")

# Auth
@app.post("/api/auth/login")
def login(c: LoginReq, response: Response):
    u = db_query("SELECT * FROM users WHERE username = ?", (c.username,), one=True)
    if not u or not verify_password(u["password_hash"], u["salt"], c.password):
        raise HTTPException(400, "Invalid username or password")
    token = create_session(u["id"])
    response.set_cookie("session_token", token, httponly=True, samesite="lax")
    return {"token": token, "user": {"id": u["id"], "username": u["username"], "role": u["role"], "full_name": u["full_name"], "email": u["email"]}}

@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    auth = request.headers.get("Authorization")
    token = auth.split(" ")[1] if (auth and auth.startswith("Bearer ")) else request.cookies.get("session_token")
    if token: delete_session(token)
    response.delete_cookie("session_token")
    return {"message": "Logged out successfully"}

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"user": user}

# Bank Info
@app.get("/api/bank/info")
def get_bank_info():
    info = db_query("SELECT * FROM bank_info WHERE id = 1", one=True)
    if not info: raise HTTPException(404, "Bank information not found")
    return info

@app.put("/api/bank/info")
def update_bank_info(p: BankInfoReq, admin: dict = Depends(get_admin_user)):
    now = datetime.now(timezone.utc).isoformat()
    db_execute("""UPDATE bank_info SET bank_name=?, branch_name=?, ifsc_code=?, swift_code=?, routing_number=?,
               support_email=?, support_phone=?, address=?, reserve_ratio=?, updated_at=? WHERE id=1""",
               (p.bank_name, p.branch_name, p.ifsc_code, p.swift_code, p.routing_number, p.support_email, p.support_phone, p.address, p.reserve_ratio, now))
    return {"message": "Bank details updated successfully"}

# Admin
@app.get("/api/admin/metrics")
def get_admin_metrics(admin: dict = Depends(get_admin_user)):
    a = db_query("SELECT COUNT(*) c, SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) a, COALESCE(SUM(balance), 0) b FROM accounts", one=True)
    t = db_query("SELECT COUNT(*) c, COALESCE(SUM(amount), 0) v FROM transactions", one=True)
    return {"total_accounts": a["c"], "active_accounts": a["a"], "frozen_accounts": a["c"] - a["a"],
            "total_vault_deposits": round(a["b"], 2), "total_transactions": t["c"], "total_volume": round(t["v"], 2)}

@app.get("/api/admin/accounts")
def list_admin_accounts(admin: dict = Depends(get_admin_user)):
    return db_query("""SELECT a.*, u.id as user_id, u.username, u.full_name, u.email, u.phone 
                    FROM accounts a JOIN users u ON a.user_id = u.id ORDER BY a.id DESC""")

@app.post("/api/admin/accounts")
def create_customer_account(p: CreateCustomerReq, admin: dict = Depends(get_admin_user)):
    if db_query("SELECT id FROM users WHERE username = ? OR email = ?", (p.username, p.email), one=True):
        raise HTTPException(400, "Username or Email already registered")
    now, (pwd_hash, salt) = datetime.now(timezone.utc).isoformat(), hash_password(p.password)
    uid = db_execute("INSERT INTO users VALUES (NULL, ?, ?, ?, 'user', ?, ?, ?, ?)", (p.username, pwd_hash, salt, p.full_name, p.email, p.phone, now))
    acc_num = f"ACC-{secrets.randbelow(90000000) + 10000000}"
    aid = db_execute("INSERT INTO accounts VALUES (NULL, ?, ?, ?, ?, 'active', ?)", (uid, acc_num, p.account_type, p.initial_deposit, now))
    if p.initial_deposit > 0:
        db_execute("INSERT INTO transactions VALUES (NULL, ?, NULL, ?, 'deposit', ?, 'Initial Account Opening Deposit', ?)",
                   ("TXN-" + secrets.token_hex(4).upper(), aid, p.initial_deposit, now))
    return {"message": "Customer account created successfully", "account_number": acc_num}

@app.patch("/api/admin/accounts/{account_number}/status")
def toggle_account_status(account_number: str, p: StatusReq, admin: dict = Depends(get_admin_user)):
    if not db_query("SELECT id FROM accounts WHERE account_number = ?", (account_number,), one=True):
        raise HTTPException(404, "Account not found")
    db_execute("UPDATE accounts SET status = ? WHERE account_number = ?", (p.status, account_number))
    return {"message": f"Account status updated to {p.status}"}

@app.get("/api/admin/transactions")
def list_all_transactions(admin: dict = Depends(get_admin_user)):
    return db_query("""SELECT t.*, fa.account_number as from_account_number, fu.full_name as from_user_name,
                    ta.account_number as to_account_number, tu.full_name as to_user_name
                    FROM transactions t LEFT JOIN accounts fa ON t.from_account_id = fa.id
                    LEFT JOIN users fu ON fa.user_id = fu.id LEFT JOIN accounts ta ON t.to_account_id = ta.id
                    LEFT JOIN users tu ON ta.user_id = tu.id ORDER BY t.id DESC LIMIT 200""")

# Customer
@app.get("/api/user/account")
def get_user_account(user: dict = Depends(get_current_user)):
    acc = db_query("SELECT a.*, b.bank_name, b.branch_name, b.ifsc_code, b.swift_code FROM accounts a CROSS JOIN bank_info b WHERE a.user_id = ? AND b.id = 1", (user["id"],), one=True)
    if not acc: raise HTTPException(404, "No active bank account associated with this profile")
    c = acc["account_number"].replace("ACC-", "")
    return {**acc, "user_full_name": user["full_name"], "user_email": user["email"], "user_phone": user.get("phone", "N/A"),
            "card_number": f"4892 {c[:4]} {c[4:8]} 9012", "card_expiry": "11/29", "card_type": "Apex Platinum Debit"}

@app.get("/api/user/lookup-account/{account_number}")
def lookup_account(account_number: str, user: dict = Depends(get_current_user)):
    dest = db_query("SELECT a.account_number, a.status, u.full_name as recipient_name FROM accounts a JOIN users u ON a.user_id = u.id WHERE a.account_number = ?", (account_number.strip(),), one=True)
    if not dest: raise HTTPException(404, "Destination account does not exist")
    if dest["status"] != "active": raise HTTPException(400, "Destination account is currently frozen or inactive")
    return dest

@app.post("/api/user/deposit")
def user_deposit(p: DepositReq, user: dict = Depends(get_current_user)):
    acc = db_query("SELECT id, balance, status FROM accounts WHERE user_id = ?", (user["id"],), one=True)
    if not acc or acc["status"] != "active": raise HTTPException(400, "Account frozen or not found")
    new_bal, ref, now = round(acc["balance"] + p.amount, 2), "TXN-" + secrets.token_hex(4).upper(), datetime.now(timezone.utc).isoformat()
    db_execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_bal, acc["id"]))
    db_execute("INSERT INTO transactions VALUES (NULL, ?, NULL, ?, 'deposit', ?, ?, ?)", (ref, acc["id"], p.amount, p.description or "Online Deposit", now))
    return {"message": f"Successfully deposited ₹{p.amount:,.2f}", "reference_id": ref, "new_balance": new_bal}

@app.post("/api/user/withdraw")
def user_withdraw(p: WithdrawReq, user: dict = Depends(get_current_user)):
    acc = db_query("SELECT id, balance, status FROM accounts WHERE user_id = ?", (user["id"],), one=True)
    if not acc or acc["status"] != "active": raise HTTPException(400, "Account frozen or not found")
    if acc["balance"] < p.amount: raise HTTPException(400, f"Insufficient balance. Current balance: ₹{acc['balance']:,.2f}")
    new_bal, ref, now = round(acc["balance"] - p.amount, 2), "TXN-" + secrets.token_hex(4).upper(), datetime.now(timezone.utc).isoformat()
    db_execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_bal, acc["id"]))
    db_execute("INSERT INTO transactions VALUES (NULL, ?, ?, NULL, 'withdrawal', ?, ?, ?)", (ref, acc["id"], p.amount, p.description or "ATM Withdrawal", now))
    return {"message": f"Successfully withdrawn ₹{p.amount:,.2f}", "reference_id": ref, "new_balance": new_bal}

@app.post("/api/user/transfer")
def user_transfer(p: TransferReq, user: dict = Depends(get_current_user)):
    src = db_query("SELECT id, account_number, balance, status FROM accounts WHERE user_id = ?", (user["id"],), one=True)
    if not src or src["status"] != "active": raise HTTPException(400, "Account inactive or frozen")
    t_acc = p.to_account_number.strip()
    if t_acc == src["account_number"]: raise HTTPException(400, "Cannot transfer funds to the same account")
    dest = db_query("SELECT id, balance, status FROM accounts WHERE account_number = ?", (t_acc,), one=True)
    if not dest: raise HTTPException(404, "Destination account not found")
    if dest["status"] != "active": raise HTTPException(400, "Destination account is inactive or frozen")
    if src["balance"] < p.amount: raise HTTPException(400, f"Insufficient balance. Current balance: ₹{src['balance']:,.2f}")
    new_src, new_dest = round(src["balance"] - p.amount, 2), round(dest["balance"] + p.amount, 2)
    ref, now = "TXN-" + secrets.token_hex(4).upper(), datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_src, src["id"]))
        conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_dest, dest["id"]))
        conn.execute("INSERT INTO transactions VALUES (NULL, ?, ?, ?, 'transfer', ?, ?, ?)", (ref, src["id"], dest["id"], p.amount, p.description or "Peer Transfer", now))
        conn.commit()
    return {"message": f"Successfully transferred ₹{p.amount:,.2f} to {t_acc}", "reference_id": ref, "new_balance": new_src}

@app.get("/api/user/transactions")
def get_user_transactions(user: dict = Depends(get_current_user)):
    acc = db_query("SELECT id FROM accounts WHERE user_id = ?", (user["id"],), one=True)
    if not acc: return []
    aid = acc["id"]
    txs = db_query("""SELECT t.*, fa.account_number as from_account_number, fu.full_name as from_user_name,
                   ta.account_number as to_account_number, tu.full_name as to_user_name
                   FROM transactions t LEFT JOIN accounts fa ON t.from_account_id = fa.id
                   LEFT JOIN users fu ON fa.user_id = fu.id LEFT JOIN accounts ta ON t.to_account_id = ta.id
                   LEFT JOIN users tu ON ta.user_id = tu.id WHERE t.from_account_id = ? OR t.to_account_id = ?
                   ORDER BY t.id DESC LIMIT 100""", (aid, aid))
    for t in txs: t["flow"] = "credit" if (t["transaction_type"] == "deposit" or t["to_account_id"] == aid) else "debit"
    return txs

@app.get("/", response_class=HTMLResponse)
def index_view():
    with open(os.path.join(os.path.dirname(__file__), "templates", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
