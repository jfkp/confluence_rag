FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y gcc libffi-dev && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Default entrypoint: run full ingestion
CMD ["python", "confluence_ingest.py"]
