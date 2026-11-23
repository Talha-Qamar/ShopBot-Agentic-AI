"""
ShopBot FastAPI Server.
Exposes required endpoints for automated grading and serves full Customer Storefront and Seller Admin Dashboard:
- POST /chat : {"user_id": "...", "thread_id": "...", "message": "..."} -> {"reply": "...", "tool_calls": [...], "tokens": {"in": int, "out": int}}
- GET /health: returns "ok"
- Storefront & Admin APIs
"""

import os
import sys
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Ensure shopbot root is on python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopbot.agent import run_shopbot_agent
from shopbot.database import (
    search_products,
    get_product_by_id,
    get_user_orders,
    get_all_orders_admin,
    get_admin_metrics,
    get_user_profile,
    get_connection,
    USE_POSTGRES
)

app = FastAPI(
    title="ShopBot Agent API & Storefront",
    description="Design to Production Hackathon: AI Storefront with Sales Agent",
    version="1.0.0"
)

# Enable CORS for frontend flexibility (Vercel, local, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Required API Schemas
class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Unique customer user ID")
    thread_id: str = Field(..., description="Unique conversation session thread ID")
    message: str = Field(..., description="Message input from customer")


class TokenUsage(BaseModel):
    in_: int = Field(0, alias="in")
    out: int = Field(0, alias="out")

    class Config:
        populate_by_name = True


class ChatResponse(BaseModel):
    reply: str
    tool_calls: List[Dict[str, Any]]
    tokens: Dict[str, int]


# 1. REQUIRED ENDPOINTS FOR GRADING

@app.get("/health", response_class=PlainTextResponse)
def health_check():
    """Returns 'ok' as strictly required by hackathon specification."""
    return "ok"


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest):
    """
    Main Agent Endpoint for automated grading and live chat:
    Receives user_id, thread_id, message.
    Returns reply, tool_calls, tokens.
    """
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    result = run_shopbot_agent(
        user_id=payload.user_id,
        thread_id=payload.thread_id,
        message=payload.message
    )

    return ChatResponse(
        reply=result["reply"],
        tool_calls=result["tool_calls"],
        tokens=result["tokens"]
    )


# 2. STOREFRONT & ADMIN APIS

@app.get("/api/products")
def list_products(query: Optional[str] = None, category: Optional[str] = None):
    """Returns products for the customer storefront."""
    return search_products(query=query, category=category)


@app.get("/api/orders")
def list_user_orders(user_id: str = Query(..., description="User ID for isolated orders")):
    """Returns orders strictly isolated for the given user_id."""
    return get_user_orders(user_id=user_id)


@app.get("/api/profile")
def get_profile(user_id: str = Query(..., description="User ID for profile")):
    """Returns persistent long-term memory for user_id."""
    return get_user_profile(user_id=user_id)


@app.get("/api/admin/metrics")
def admin_metrics():
    """Returns store overview metrics for Seller Admin Dashboard."""
    return get_admin_metrics()


@app.get("/api/admin/orders")
def admin_orders():
    """Returns all store orders for Seller Admin Dashboard."""
    return get_all_orders_admin()


@app.get("/api/admin/users")
def admin_users():
    """Returns all customer profiles and long-term memory records."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id, preferences_json, last_active FROM user_profiles ORDER BY last_active DESC")
    rows = cur.fetchall()
    users = []
    for r in rows:
        import json
        try:
            prefs = json.loads(r[1])
        except Exception:
            prefs = {}
        users.append({
            "user_id": r[0],
            "preferences": prefs,
            "last_active": str(r[2])
        })
    conn.close()
    return users


# Static assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def serve_customer_storefront():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "ShopBot API is running. Go to /static/index.html or /docs"}


@app.get("/admin")
def serve_admin_dashboard():
    admin_file = os.path.join(static_dir, "admin.html")
    if os.path.exists(admin_file):
        return FileResponse(admin_file)
    return {"message": "Admin Dashboard. Go to /static/admin.html"}
