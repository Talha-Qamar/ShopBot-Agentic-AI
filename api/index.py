import sys
import os

# Add root directory to python path for Vercel Serverless Functions
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopbot.main import app
