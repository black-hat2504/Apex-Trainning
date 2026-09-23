import os
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_system():
    print("Testing Bank Info...")
    res = client.get("/api/bank/info")
    assert res.status_code == 200, f"Failed: {res.text}"
    bank_data = res.json()
    print("Bank Info OK:", bank_data["bank_name"], bank_data["ifsc_code"])

    print("\nTesting Admin Login...")
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    admin_token = res.json()["token"]
    print("Admin Token acquired successfully")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/admin/metrics", headers=admin_headers)
    assert res.status_code == 200, f"Admin metrics failed: {res.text}"
    print("Admin Metrics OK:", res.json())

    res = client.get("/api/admin/accounts", headers=admin_headers)
    assert res.status_code == 200
    accounts = res.json()
    print(f"Admin Accounts list retrieved: {len(accounts)} accounts found")

    print("\nTesting User Login (john_doe)...")
    res = client.post("/api/auth/login", json={"username": "john_doe", "password": "user123"})
    assert res.status_code == 200
    user_token = res.json()["token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}

    res = client.get("/api/user/account", headers=user_headers)
    assert res.status_code == 200
    user_acc = res.json()
    initial_balance = user_acc["balance"]
    print(f"User Account retrieved: {user_acc['account_number']}, Balance: ${initial_balance:,.2f}")

    print("\nTesting Deposit $250.00...")
    res = client.post("/api/user/deposit", json={"amount": 250.0, "description": "Test Deposit"}, headers=user_headers)
    assert res.status_code == 200
    deposit_res = res.json()
    assert deposit_res["new_balance"] == round(initial_balance + 250.0, 2)
    print("Deposit OK, New Balance:", deposit_res["new_balance"])

    print("\nTesting Withdrawal $50.00...")
    res = client.post("/api/user/withdraw", json={"amount": 50.0, "description": "Test Withdrawal"}, headers=user_headers)
    assert res.status_code == 200
    withdraw_res = res.json()
    assert withdraw_res["new_balance"] == round(deposit_res["new_balance"] - 50.0, 2)
    print("Withdrawal OK, New Balance:", withdraw_res["new_balance"])

    print("\nTesting Transfer $100.00 from John to Sarah (ACC-91204851)...")
    res = client.post("/api/user/transfer", json={
        "to_account_number": "ACC-91204851",
        "amount": 100.0,
        "description": "Test Peer Transfer"
    }, headers=user_headers)
    assert res.status_code == 200
    msg = res.json()["message"]
    assert "₹" in msg, f"Expected ₹ in response message, got: {msg}"
    print("Transfer OK:", msg)

    print("\nTesting User Transactions list...")
    res = client.get("/api/user/transactions", headers=user_headers)
    assert res.status_code == 200
    txs = res.json()
    assert len(txs) > 0
    print(f"Transactions retrieved: {len(txs)} txs recorded. Latest: {txs[0]['reference_id']} ({txs[0]['flow']} ₹{txs[0]['amount']})")

    print("\nTesting Frontend HTML Root (/)...")
    res = client.get("/")
    assert res.status_code == 200
    assert "Apex Global Trust" in res.text
    assert "₹" in res.text
    print("Frontend HTML loaded successfully with ₹ Indian Rupees!")

    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_system()
