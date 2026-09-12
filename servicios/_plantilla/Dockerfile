FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
ENV PYTHONPATH=/app/src

# El nombre del paquete se fija al copiar la plantilla.
ARG SERVICIO=servicio_plantilla
ENV SERVICIO=${SERVICIO}

# Una imagen, dos tipos de proceso: `api` (gunicorn) y `consumidor`.
ENV MODO=api

EXPOSE 5000

CMD ["sh", "-c", "if [ \"$MODO\" = consumidor ]; then exec python -m $SERVICIO.consumidor; else exec gunicorn -w ${WORKERS:-2} -b 0.0.0.0:5000 \"$SERVICIO:crear_app()\"; fi"]
