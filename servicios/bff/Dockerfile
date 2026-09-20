FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
ENV PYTHONPATH=/app/src

EXPOSE 5000

# `gthread`: un servicio de atrás lento no debe dejar sin atender `/health`.
CMD ["sh", "-c", "exec gunicorn --worker-class gthread -w ${WORKERS:-2} --threads ${THREADS:-8} -b 0.0.0.0:5000 \"bff:crear_app()\""]
