"""
ShopBot Entrypoint.
Runs the FastAPI web server hosting both the agent API and customer storefront / admin dashboard.
"""

import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"\n" + "="*70)
    print(f"🚀 Launching ShopBot on http://localhost:{port}")
    print(f"• Customer Storefront:     http://localhost:{port}/")
    print(f"• Seller Admin Dashboard:  http://localhost:{port}/admin")
    print(f"• Health Check:            http://localhost:{port}/health")
    print(f"• Chat Agent Endpoint:     http://localhost:{port}/chat (POST)")
    print(f"• Interactive Swagger API: http://localhost:{port}/docs")
    print("="*70 + "\n")
    uvicorn.run("shopbot.main:app", host="0.0.0.0", port=port, reload=True)
