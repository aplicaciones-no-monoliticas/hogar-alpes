#!/usr/bin/env bash
# DEP-1 · Aprovisionamiento de la EC2 — Hogar de los Alpes, Entrega 4.
#
# Pensado como `user-data` de una instancia Ubuntu 24.04 (EC2 t3.xlarge, 4
# vCPU / 16 GB, disco gp3 de 40 GB — plan técnico §6.2): instala Docker y el
# plugin de Compose, clona el repositorio PÚBLICO, genera credenciales de base
# de datos que no vienen del repositorio, y levanta el sistema completo.
#
# No lleva secretos: las credenciales se generan EN LA INSTANCIA, en `.env`
# (ignorado por git, RNF-6). Nada de esto se commitea.
#
# Uso como user-data (al lanzar la instancia, en la consola o con
# `aws ec2 run-instances --user-data file://infra/aws/user-data.sh`):
# la instancia se aprovisiona sola en el primer arranque.
#
# Uso manual, sobre una instancia ya corriendo:
#   curl -fsSL https://raw.githubusercontent.com/aplicaciones-no-monoliticas/hogar-alpes/main/infra/aws/user-data.sh | bash

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/aplicaciones-no-monoliticas/hogar-alpes.git}"
DESTINO="${DESTINO:-/opt/hogar-alpes}"

echo "== Docker + plugin de Compose =="
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  usermod -aG docker "${SUDO_USER:-ubuntu}" || true
fi

echo "== Clonar el repositorio =="
if [ ! -d "$DESTINO/.git" ]; then
  git clone --depth 1 "$REPO_URL" "$DESTINO"
else
  git -C "$DESTINO" pull --ff-only
fi
cd "$DESTINO"

echo "== Python para herramientas/ (escenarios 6 y 8 corren por SSH, no en Docker) =="
# pulsar-client necesita compilar contra binarios propios: python3-venv +
# python3-pip de Ubuntu alcanzan, no hace falta build-essential.
if [ ! -d "$DESTINO/.venv" ]; then
  apt-get update -y
  apt-get install -y python3-venv python3-pip
  python3 -m venv "$DESTINO/.venv"
  "$DESTINO/.venv/bin/pip" install --upgrade pip
  "$DESTINO/.venv/bin/pip" install -r "$DESTINO/herramientas/requirements.txt"
else
  echo "$DESTINO/.venv ya existe, no se toca."
fi

echo "== Generar .env con credenciales propias de esta instancia =="
if [ ! -f .env ]; then
  cp .env.example .env
  # Contraseña de base de datos generada aquí, no en el repositorio (RNF-6).
  CLAVE="$(openssl rand -hex 24)"
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${CLAVE}/" .env
  echo "Generado .env con una contraseña nueva (no impresa en este log)."
else
  echo ".env ya existe, no se toca."
fi

echo "== docker compose up -d =="
# El mismo artefacto que corre en el portátil del equipo: ningún archivo de
# Compose distinto para "producción" (plan técnico §6.2).
docker compose up -d

echo "== Listo =="
echo "Las cuatro API deberían responder en unos minutos en los puertos 8000-8003."
echo "Ver infra/aws/README.md para el resto (security group, verificación, apagado)."
