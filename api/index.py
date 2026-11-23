import sys
import os
import urllib.parse

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
    Extracts the original requested path passed via __path__=$1 in vercel.json
    or from Vercel's x-matched-path / x-forwarded-uri headers, ensuring
    exact FastAPI routing across all endpoints (/health, /admin, /api/products, etc.).
    """
    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            raw_qs = scope.get("query_string", b"").decode("latin1")
            parsed_qs = urllib.parse.parse_qs(raw_qs)
            
            target_path = None
            if "__path__" in parsed_qs:
                target_path = "/" + parsed_qs.pop("__path__", [""])[0].lstrip("/")
                # Clean __path__ out of query string so endpoint params remain clean
                clean_qs = urllib.parse.urlencode([(k, v) for k, vs in parsed_qs.items() for v in vs])
                scope["query_string"] = clean_qs.encode("latin1")

            # Fallback to headers if __path__ was not in query string
            if not target_path:
                headers = dict(scope.get("headers", []))
                header_map = {k.decode("latin1").lower(): v.decode("latin1") for k, v in headers.items()}
                matched = (
                    header_map.get("x-matched-path")
                    or header_map.get("x-forwarded-uri")
                    or header_map.get("x-original-url")
                )
                if matched:
                    target_path = matched.split("?")[0]

            current_path = scope.get("path", "")
            if target_path:
                scope["path"] = target_path
                scope["raw_path"] = target_path.encode("latin1")
            elif current_path in ["/api/index.py", "/api/index", "/api"] or current_path.endswith(".py"):
                scope["path"] = "/"
                scope["raw_path"] = b"/"

        await self.asgi_app(scope, receive, send)


app = VercelRoutingMiddleware(fastapi_app)
