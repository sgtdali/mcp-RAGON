# Dockerfile for Render Deployment
FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose port
EXPOSE 8000

# Start Command (Uvicorn)
CMD ["uvicorn", "mcp_server:app", "--host", "0.0.0.0", "--port", "8000"]
