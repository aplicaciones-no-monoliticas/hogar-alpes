FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
ENV PYTHONPATH=/app/src
ENV FLASK_APP=gestion_trabajos

# Una imagen, dos tipos de proceso. Sigue siendo UN microservicio: mismo código
# y misma base de datos, con dos roles que escalan por separado.
ENV MODO=api

EXPOSE 5000

CMD ["sh", "-c", "if [ \"$MODO\" = consumidor ]; then exec python -m gestion_trabajos.consumidor; else exec gunicorn -w ${WORKERS:-2} -b 0.0.0.0:5000 'gestion_trabajos:crear_app()'; fi"]
