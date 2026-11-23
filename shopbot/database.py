"""
ShopBot Database & Persistent Storage Module.
Supports both SQLite (local/fallback) and PostgreSQL (Supabase / Neon via DATABASE_URL).
Implements strict isolation per user_id and persistent long-term memory across sessions.
"""

import os
import json
import sqlite3
import datetime
from typing import Dict, List, Optional, Any

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgres"))

# Support writable path for serverless runtimes like Vercel / AWS Lambda
IS_SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
if IS_SERVERLESS:
    DB_FILE = "/tmp/shopbot.db"
else:
    DB_FILE = os.path.join(os.path.dirname(__file__), "shopbot.db")


def get_connection():
    """Returns database connection based on environment configuration."""
    if USE_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    """Initializes tables and seeds initial store catalog."""
    conn = get_connection()
    cur = conn.cursor()

    if USE_POSTGRES:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                category VARCHAR(100) NOT NULL,
                price NUMERIC(10, 2) NOT NULL,
                stock INTEGER NOT NULL,
                description TEXT,
                image_url TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id VARCHAR(50) PRIMARY KEY,
                user_id VARCHAR(100) NOT NULL,
                items_json TEXT NOT NULL,
                total_amount NUMERIC(10, 2) NOT NULL,
                shipping_address TEXT NOT NULL,
                status VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id VARCHAR(100) PRIMARY KEY,
                preferences_json TEXT NOT NULL,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(100),
                thread_id VARCHAR(100),
                action VARCHAR(100),
                details_json TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL,
                description TEXT,
                image_url TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                items_json TEXT NOT NULL,
                total_amount REAL NOT NULL,
                shipping_address TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                preferences_json TEXT NOT NULL,
                last_active TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                thread_id TEXT,
                action TEXT,
                details_json TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

    conn.commit()

    # Ensure all seed products exist (insert if not present)
    seed_products = [
        ("prod_1", "Artisan Dark Roast Coffee", "Coffee", 18.50, 45, "Rich, full-bodied dark roast with notes of dark chocolate and caramel. 12oz whole bean.", "https://images.unsplash.com/photo-1559056199-641a0ac8b55e?w=500&q=80"),
        ("prod_2", "Single-Origin Ethiopian Light Roast", "Coffee", 21.00, 30, "Floral and fruity tasting notes of bergamot and blueberry. 12oz whole bean.", "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=500&q=80"),
        ("prod_3", "Ceramic Pour-Over Coffee Dripper", "Brewing Gear", 28.00, 15, "Handcrafted ceramic pour-over cone for maximum temperature stability.", "https://images.unsplash.com/photo-1544787219-7f47ccb76574?w=500&q=80"),
        ("prod_4", "Barista Grade Stainless Kettle", "Brewing Gear", 48.00, 12, "Gooseneck temperature-control kettle for precise pour flow.", "https://images.unsplash.com/photo-1578314675249-a6910f80cc4e?w=500&q=80"),
        ("prod_5", "Double-Walled Insulated Travel Tumbler", "Drinkware", 24.50, 50, "16oz leak-proof vacuum tumbler keeps coffee piping hot for 8 hours.", "https://images.unsplash.com/photo-1517256064527-09c73fc73e38?w=500&q=80"),
        ("prod_6", "Organic Oat Milk Barista Edition (Pack of 6)", "Pantry", 19.99, 25, "Creamy plant-based milk designed for foaming silky microfoam.", "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=500&q=80"),
        ("prod_7", "Digital Precision Coffee Scale & Timer", "Brewing Gear", 32.00, 20, "Measures to 0.1g accuracy with built-in auto-tare and extraction timer.", "https://images.unsplash.com/photo-1511920170033-f8396924c348?w=500&q=80"),
        ("prod_8", "Fresh French Butter Croissants (Box of 4)", "Food & Bakery", 14.50, 25, "Flaky, golden all-butter croissants freshly baked every morning. Perfect paired with artisan espresso.", "https://images.unsplash.com/photo-1555507036-ab1f4038808a?w=500&q=80"),
        ("prod_9", "Dark Chocolate Espresso Biscotti (Pack of 6)", "Food & Bakery", 11.00, 35, "Twice-baked almond biscotti dipped in 70% dark chocolate. Designed for dunking.", "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=500&q=80"),
        ("prod_10", "Artisan Caramel Stroopwafels (Box of 8)", "Food & Bakery", 12.99, 40, "Authentic Dutch cinnamon-spiced waffles with gooey brown sugar caramel filling.", "https://images.unsplash.com/photo-1587314168485-3236d6710814?w=500&q=80"),
        ("prod_11", "Organic Wildflower Honey & Granola", "Food & Bakery", 13.50, 20, "Handmade toasted rolled oats, walnuts, and dried cherries drizzled with pure wildflower honey.", "https://images.unsplash.com/photo-1517093157656-b9ec80c58e51?w=500&q=80"),
        ("prod_12", "Single-Origin 85% Dark Chocolate Bar", "Food & Bakery", 8.50, 50, "Bean-to-bar fair trade dark chocolate with notes of roasted cacao and dried plum.", "https://images.unsplash.com/photo-1548907040-4baa42d10919?w=500&q=80")
    ]
    for p in seed_products:
        if USE_POSTGRES:
            cur.execute("""
                INSERT INTO products (id, name, category, price, stock, description, image_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, p)
        else:
            cur.execute("""
                INSERT OR IGNORE INTO products (id, name, category, price, stock, description, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, p)
    conn.commit()

    conn.close()


# Product Queries
def search_products(query: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    sql = "SELECT id, name, category, price, stock, description, image_url FROM products WHERE stock > 0"
    params = []

    if category:
        sql += " AND LOWER(category) = LOWER(%s)" if USE_POSTGRES else " AND LOWER(category) = LOWER(?)"
        params.append(category)
    if query:
        q = f"%{query}%"
        sql += " AND (LOWER(name) LIKE LOWER(%s) OR LOWER(description) LIKE LOWER(%s))" if USE_POSTGRES else " AND (LOWER(name) LIKE LOWER(?) OR LOWER(description) LIKE LOWER(?))"
        params.extend([q, q])

    cur.execute(sql, params)
    rows = cur.fetchall()
    results = []
    for r in rows:
        results.append({
            "id": r[0], "name": r[1], "category": r[2],
            "price": float(r[3]), "stock": int(r[4]),
            "description": r[5], "image_url": r[6]
        })
    conn.close()

    # Safeguard for cold serverless boots: initialize if table was empty
    if not results and not query and not category:
        try:
            init_db()
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            for r in rows:
                results.append({
                    "id": r[0], "name": r[1], "category": r[2],
                    "price": float(r[3]), "stock": int(r[4]),
                    "description": r[5], "image_url": r[6]
                })
            conn.close()
        except Exception:
            pass

    return results


def get_product_by_id(product_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, category, price, stock, description, image_url FROM products WHERE id = %s" if USE_POSTGRES else
        "SELECT id, name, category, price, stock, description, image_url FROM products WHERE id = ?",
        (product_id,)
    )
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    return {
        "id": r[0], "name": r[1], "category": r[2],
        "price": float(r[3]), "stock": int(r[4]),
        "description": r[5], "image_url": r[6]
    }


# Long-Term Memory Storage (Per user_id)
def get_user_profile(user_id: str) -> Dict[str, Any]:
    """Retrieves persistent long-term memory for a given user."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT preferences_json FROM user_profiles WHERE user_id = %s" if USE_POSTGRES else
        "SELECT preferences_json FROM user_profiles WHERE user_id = ?",
        (user_id,)
    )
    r = cur.fetchone()
    conn.close()
    if r and r[0]:
        try:
            return json.loads(r[0])
        except Exception:
            return {}
    return {}


def save_user_profile(user_id: str, preferences: Dict[str, Any]):
    """Persists long-term memory across sessions for a given user."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    raw_json = json.dumps(preferences)

    if USE_POSTGRES:
        cur.execute("""
            INSERT INTO user_profiles (user_id, preferences_json, last_active)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET preferences_json = %s, last_active = %s
        """, (user_id, raw_json, now, raw_json, now))
    else:
        cur.execute("""
            INSERT INTO user_profiles (user_id, preferences_json, last_active)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET preferences_json = ?, last_active = ?
        """, (user_id, raw_json, now, raw_json, now))
    conn.commit()
    conn.close()


# Orders & Transactions (Isolated per user_id)
def create_order_record(user_id: str, items: List[Dict[str, Any]], total_amount: float, shipping_address: str) -> Dict[str, Any]:
    """Records an order and decrements inventory."""
    conn = get_connection()
    cur = conn.cursor()
    order_id = f"ord_{int(datetime.datetime.utcnow().timestamp())}_{os.urandom(2).hex()}"
    items_json = json.dumps(items)
    now = datetime.datetime.utcnow().isoformat()

    # Decrement inventory
    for it in items:
        prod_id = it.get("product_id") or it.get("id")
        qty = int(it.get("quantity", 1))
        if prod_id:
            cur.execute(
                "UPDATE products SET stock = MAX(0, stock - %s) WHERE id = %s" if USE_POSTGRES else
                "UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?",
                (qty, prod_id)
            )

    # Insert order
    cur.execute(
        """
        INSERT INTO orders (id, user_id, items_json, total_amount, shipping_address, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """ if USE_POSTGRES else
        """
        INSERT INTO orders (id, user_id, items_json, total_amount, shipping_address, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (order_id, user_id, items_json, total_amount, shipping_address, "confirmed", now)
    )

    conn.commit()
    conn.close()

    return {
        "order_id": order_id,
        "user_id": user_id,
        "items": items,
        "total_amount": total_amount,
        "shipping_address": shipping_address,
        "status": "confirmed",
        "created_at": now
    }


def get_user_orders(user_id: str) -> List[Dict[str, Any]]:
    """Strictly isolated per user_id: Returns only orders belonging to user_id."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id, items_json, total_amount, shipping_address, status, created_at FROM orders WHERE user_id = %s ORDER BY created_at DESC" if USE_POSTGRES else
        "SELECT id, user_id, items_json, total_amount, shipping_address, status, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )
    rows = cur.fetchall()
    orders = []
    for r in rows:
        try:
            it = json.loads(r[2])
        except Exception:
            it = []
        orders.append({
            "id": r[0],
            "user_id": r[1],
            "items": it,
            "total_amount": float(r[3]),
            "shipping_address": r[4],
            "status": r[5],
            "created_at": str(r[6])
        })
    conn.close()
    return orders


def get_all_orders_admin() -> List[Dict[str, Any]]:
    """Admin only: returns all store orders."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, items_json, total_amount, shipping_address, status, created_at FROM orders ORDER BY created_at DESC")
    rows = cur.fetchall()
    orders = []
    for r in rows:
        try:
            it = json.loads(r[2])
        except Exception:
            it = []
        orders.append({
            "id": r[0],
            "user_id": r[1],
            "items": it,
            "total_amount": float(r[3]),
            "shipping_address": r[4],
            "status": r[5],
            "created_at": str(r[6])
        })
    conn.close()
    return orders


def get_admin_metrics() -> Dict[str, Any]:
    """Computes store analytics for the admin dashboard."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM orders")
    order_count, total_revenue = cur.fetchone()

    cur.execute("SELECT COUNT(*), COALESCE(SUM(stock), 0) FROM products")
    product_count, total_units = cur.fetchone()

    cur.execute("SELECT COUNT(*) FROM user_profiles")
    total_customers = cur.fetchone()[0]

    conn.close()
    return {
        "total_orders": int(order_count or 0),
        "total_revenue": round(float(total_revenue or 0), 2),
        "total_products": int(product_count or 0),
        "inventory_units": int(total_units or 0),
        "total_customers": int(total_customers or 0)
    }


# Initialize DB automatically on load
init_db()
