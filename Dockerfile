# syntax=docker/dockerfile:1

# --- Etapa de construcción: instala solo dependencias de ejecución en un venv ---
FROM python:3.12-slim AS builder

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
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
