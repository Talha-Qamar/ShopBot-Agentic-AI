import sys
import os

# Add root directory to python path for Vercel Serverless Functions
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from shopbot.main import app as fastapi_app
from shopbot.database import init_db

# Initialize database tables on serverless boot
try:
    init_db()
except Exception as e:
    print(f"Warning: init_db failed on boot: {e}")


class VercelRoutingMiddleware:
    """
    Middleware to resolve Vercel serverless rewrite paths.
    Vercel rewrites often set scope['path'] to the destination file ('/api/index.py').
    This middleware restores the original requested path from Vercel's 'x-matched-path'
    or 'x-forwarded-uri' headers so Starlette/FastAPI route matching works perfectly.
    """
    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            header_map = {k.decode("latin1").lower(): v.decode("latin1") for k, v in headers.items()}
            
            # Check original path from Vercel
            matched_path = (
                header_map.get("x-matched-path")
                or header_map.get("x-forwarded-uri")
                or header_map.get("x-original-url")
            )
            
            current_path = scope.get("path", "")
            if matched_path:
                clean_path = matched_path.split("?")[0]
                # If current_path is the entrypoint or doesn't match, map to original
                if current_path in ["/api/index.py", "/api/index", "/api", "", "/"] or current_path.endswith(".py"):
                    scope["path"] = clean_path
                    scope["raw_path"] = clean_path.encode("latin1")
            elif current_path.endswith(".py"):
                scope["path"] = "/"
                scope["raw_path"] = b"/"

        await self.asgi_app(scope, receive, send)


app = VercelRoutingMiddleware(fastapi_app)
