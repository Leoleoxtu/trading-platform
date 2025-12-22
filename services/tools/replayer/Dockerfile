FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for python-snappy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libsnappy-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

# Copy application code
COPY replayer/ ./replayer/

# Run as non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENTRYPOINT ["python", "-m", "replayer"]
