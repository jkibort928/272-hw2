# Samhitha Banda
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src ./src

# Persist webhook event store outside the image layer if you mount a volume
VOLUME ["/app/data"]

EXPOSE 8000

# PORT is read at runtime from the environment (defaults to 8000 in config.py),
# but we still expose 8000 as the conventional default for `docker run -p`.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
