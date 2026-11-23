FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications
COPY requirements.txt .

# Install dependencies including fastapi, uvicorn, langchain-anthropic
RUN pip install --no-cache-dir -r requirements.txt \
    fastapi uvicorn langchain-anthropic anthropic psycopg2-binary

# Copy application files
COPY . .

# Set environment defaults
ENV PORT=7860
ENV PYTHONUNBUFFERED=1

EXPOSE 7860

# Run FastAPI via Uvicorn
CMD ["sh", "-c", "uvicorn shopbot.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
