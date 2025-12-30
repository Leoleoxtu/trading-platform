FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including snappy for Kafka compression
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    libsnappy-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model (optional, will fallback to heuristic if not available)
# Note: This will only work if USE_SPACY=true at runtime
RUN python -m spacy download en_core_web_sm 2>/dev/null || \
    echo "⚠️  spaCy model download skipped or failed - will use heuristic fallback"

# Copy application code
COPY app.py .

# Make app executable
RUN chmod +x app.py

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-u", "app.py"]
