"""
ShopBot Tools for LangGraph Agents.
Real tools for catalog search, stock validation, price calculations, ordering, and long-term memory.
"""

from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from shopbot.database import (
    search_products,
    get_product_by_id,
    create_order_record,
    get_user_orders,
    get_user_profile,
    save_user_profile
)


@tool
def search_catalog(query: str = "", category: str = "") -> str:
    """
    Search the store product catalog by keyword or category.
    Available categories: Coffee, Brewing Gear, Drinkware, Pantry.
    """
    cleaned_query = query.strip() if query else None
    cleaned_category = category.strip() if category else None
    products = search_products(query=cleaned_query, category=cleaned_category)
    if not products:
        return "No products found matching your criteria. Try searching for Coffee, Brewing Gear, Drinkware, or Pantry."

    lines = [f"Found {len(products)} available products:"]
    for p in products:
        lines.append(f"- [{p['id']}] {p['name']} (${p['price']:.2f}) | Category: {p['category']} | In Stock: {p['stock']} | {p['description']}")
    return "\n".join(lines)


@tool
def check_inventory_and_pricing(product_id: str, quantity: int = 1, coupon_code: str = "") -> str:
    """
    Check stock availability and calculate exact pricing for a product including discounts and coupons.
    Valid coupon codes: 'WELCOME10' (10% off), 'BULK5' (5% off).
    """
    product = get_product_by_id(product_id.strip())
    if not product:
        return f"Error: Product with ID '{product_id}' was not found in catalog."

    available_stock = product["stock"]
    if available_stock < quantity:
        return f"Insufficient stock: '{product['name']}' has only {available_stock} units available (requested: {quantity})."

    unit_price = product["price"]
    subtotal = unit_price * quantity
    discount = 0.0

    # Auto bulk discount for 3+ items
    if quantity >= 3:
        discount += subtotal * 0.05

    # Coupon validation
    normalized_coupon = (coupon_code or "").strip().upper()
    if normalized_coupon == "WELCOME10":
        discount += subtotal * 0.10
    elif normalized_coupon == "BULK5":
        discount += subtotal * 0.05
    elif normalized_coupon and normalized_coupon not in ["WELCOME10", "BULK5"]:
        return f"Warning: Coupon '{coupon_code}' is invalid. Unit price is ${unit_price:.2f}. Total for {quantity} units is ${subtotal:.2f}."

    total = max(0.0, subtotal - discount)
    return (
        f"Inventory Verified: {quantity}x '{product['name']}' in stock.\n"
        f"Unit Price: ${unit_price:.2f}\n"
        f"Subtotal: ${subtotal:.2f}\n"
        f"Discount Applied: ${discount:.2f}\n"
        f"Total Price: ${total:.2f}"
    )


@tool
def save_customer_preference(user_id: str, key: str, value: str) -> str:
    """
    Save a long-term customer preference across conversations into permanent storage.
    Examples: preferred roast ('dark roast'), milk choice ('oat milk'), delivery address, favorite brew method.
    """
    if not user_id:
        return "Error: user_id is required to save customer preference."
    profile = get_user_profile(user_id)
    profile[key.strip().lower()] = value.strip()
    save_user_profile(user_id, profile)
    return f"Successfully saved customer preference '{key}': '{value}' into long-term profile."


@tool
def get_customer_history(user_id: str) -> str:
    """
    Retrieve long-term customer profile (preferences) and past orders for a user.
    Enforces user isolation: only retrieves data belonging to the specified user_id.
    """
    if not user_id:
        return "Error: user_id is required."
    profile = get_user_profile(user_id)
    orders = get_user_orders(user_id)

    sections = [f"=== Customer Profile & History for User '{user_id}' ==="]
    if profile:
        sections.append("Preferences:")
        for k, v in profile.items():
            sections.append(f"  • {k}: {v}")
    else:
        sections.append("Preferences: None saved yet.")

    if orders:
        sections.append(f"Past Orders ({len(orders)} total):")
        for o in orders[:5]:
            items_summary = ", ".join([f"{it.get('quantity', 1)}x {it.get('name', it.get('product_id'))}" for it in o.get('items', [])])
            sections.append(f"  • [{o['id']}] ${o['total_amount']:.2f} | Status: {o['status']} | Items: {items_summary} | Date: {o['created_at']}")
    else:
        sections.append("Past Orders: No previous orders found.")

    return "\n".join(sections)


@tool
def create_order(user_id: str, product_id: str, quantity: int, shipping_address: str, coupon_code: str = "") -> str:
    """
    Places an order, decrements store stock, and generates a confirmed order receipt.
    Note: Risky action! Only call this when the user has provided or confirmed purchase details.
    """
    product = get_product_by_id(product_id.strip())
    if not product:
        return f"Error: Product '{product_id}' not found."

    if product["stock"] < quantity:
        return f"Cannot place order: '{product['name']}' only has {product['stock']} units left."

    unit_price = product["price"]
    subtotal = unit_price * quantity
    discount = 0.0
    if quantity >= 3:
        discount += subtotal * 0.05
    if (coupon_code or "").strip().upper() == "WELCOME10":
        discount += subtotal * 0.10

    total_amount = round(max(0.0, subtotal - discount), 2)
    items = [{
        "product_id": product["id"],
        "name": product["name"],
        "unit_price": unit_price,
        "quantity": quantity
    }]

    order = create_order_record(
        user_id=user_id,
        items=items,
        total_amount=total_amount,
        shipping_address=shipping_address
    )

    # Automatically save shipping address into long-term memory
    profile = get_user_profile(user_id)
    profile["shipping_address"] = shipping_address
    save_user_profile(user_id, profile)

    return (
        f"🎉 Order Confirmed!\n"
        f"Order ID: {order['order_id']}\n"
        f"Items: {quantity}x {product['name']}\n"
        f"Total Charged: ${total_amount:.2f}\n"
        f"Shipping To: {shipping_address}\n"
        f"Estimated Delivery: 2-3 business days. Thank you for shopping with us!"
    )
