FROM python:3.11-slim

# Dependency untuk cairosvg (SVG → PNG)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
