# syntax=docker/dockerfile:1

# Imagen base (D3/D-6). Por defecto sigue la etiqueta mutable `python:3.12-slim`. Para un bloqueo verificable ANTES de las
# pruebas reales, fije el digest del indice multiarquitectura (valido en amd64 y arm64), por ejemplo:
#   PYTHON_IMAGE=python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b docker compose build
# (digest de python:3.12.16-slim-trixie verificado en el laboratorio de la Fase 1.0A; ver docs/decisions.md). No activado por defecto.
ARG PYTHON_IMAGE=python:3.12-slim

# --- Etapa de construcción: instala solo dependencias de ejecución en un venv ---
FROM ${PYTHON_IMAGE} AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY pyproject.toml README.md constraints.txt ./
COPY app ./app
# Se instala con constraints.txt y se falla si queda instalado algo que no figure en él.
RUN pip install -c constraints.txt . \
    && pip freeze --exclude nostr-nip46-remote-signer > /tmp/installed.txt \
    && if grep -vxFf constraints.txt /tmp/installed.txt; then \
         echo "ERROR: paquetes instalados que no coinciden con constraints.txt" >&2; exit 1; \
       fi

# --- Etapa final: imagen mínima, sin herramientas de construcción ni de desarrollo ---
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DATABASE_PATH=/data/nip46.db

# /data es el UNICO directorio escribible (volumen; el resto del sistema de archivos es de solo lectura): SQLite con el hash Argon2id del administrador.
# Se crea vacio y propiedad del usuario sin privilegios; un volumen con nombre hereda estos permisos al crearse. La imagen NO contiene credenciales.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir /data && chown 10001:10001 /data && chmod 700 /data

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
USER app

VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
