FROM python:3.12-slim

# Prevent python from buffering stdout/stderr (crucial for live docker logs)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Jakarta

WORKDIR /app

# Install system dependencies (tzdata for accurate timezone handling)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and default assets
COPY . .

# Ensure data and output directories exist
RUN mkdir -p /app/data /app/output

# Default command: run the lightweight scheduler daemon
CMD ["python", "scheduler_daemon.py"]
