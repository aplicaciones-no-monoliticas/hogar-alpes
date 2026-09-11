FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
ENV PYTHONPATH=/app/src
ENV FLASK_APP=gestion_trabajos

EXPOSE 5000
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
