"""A real local HTTP API backing the refund-agent tools, with a real SQLite database.

This turns the demo from in-memory Python functions into genuine network calls, so
agentprobe's trajectory assertions and fault injection can be proven against a live
service, not just mocked functions. `simulate_slow`/`simulate_error` let you also demo
REAL server-side flakiness, separate from agentprobe's own synthetic fault injection.

Run:
    uvicorn examples.api_server:app --port 8000 --reload
"""
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DB_PATH = Path(__file__).parent / "orders.db"


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _db()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS orders "
        "(order_id TEXT PRIMARY KEY, amount REAL NOT NULL, status TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS refunds "
        "(refund_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, amount REAL NOT NULL)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS tickets (ticket_id TEXT PRIMARY KEY, reason TEXT NOT NULL)")
    conn.execute(
        "INSERT OR IGNORE INTO orders (order_id, amount, status) VALUES (?, ?, ?)",
        ("A123", 49.99, "delivered"),
    )
    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    yield


app = FastAPI(title="agentprobe demo API", lifespan=lifespan)


@app.get("/orders/{order_id}")
def get_order(order_id: str, simulate_slow: bool = False, simulate_error: bool = False):
    if simulate_slow:
        time.sleep(3)
    if simulate_error:
        raise HTTPException(status_code=500, detail="simulated server error")

    conn = _db()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="order not found")
    return {"order_id": row["order_id"], "amount": row["amount"], "status": row["status"]}


class RefundRequest(BaseModel):
    order_id: str
    amount: float


@app.post("/refunds")
def issue_refund(req: RefundRequest):
    refund_id = f"R-{req.order_id}"
    conn = _db()
    conn.execute(
        "INSERT OR REPLACE INTO refunds (refund_id, order_id, amount) VALUES (?, ?, ?)",
        (refund_id, req.order_id, req.amount),
    )
    conn.commit()
    conn.close()
    return {"refund_id": refund_id, "amount": req.amount}


class EscalateRequest(BaseModel):
    reason: str


@app.post("/escalations")
def escalate(req: EscalateRequest):
    conn = _db()
    n = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] + 1
    ticket_id = f"T-{n}"
    conn.execute("INSERT INTO tickets (ticket_id, reason) VALUES (?, ?)", (ticket_id, req.reason))
    conn.commit()
    conn.close()
    return {"ticket": ticket_id, "reason": req.reason}


@app.delete("/accounts/{user_id}")
def delete_account(user_id: str):
    return {"deleted": user_id}
