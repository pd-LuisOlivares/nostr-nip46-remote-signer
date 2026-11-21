# Imagen Python del laboratorio. Base fijada por digest (python:3.12.16-slim-trixie, linux/amd64).
# Se construye con `network: none` (compose.yaml): instala SOLO desde lab/vendor/wheels (hashes obligatorios).
# Un unico COPY: varios COPY desde subcarpetas disparan un fallo de contexto de BuildKit en Windows.
FROM python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/lab/py

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin lab

COPY . /ctx
RUN mkdir -p /lab && mv /ctx/py /lab/py \
    # Dato local de prueba, SIN versionar (licencia sin aclarar): solo existe dentro de la imagen local.
    && mv /ctx/vendor/vectors /lab/vectors \
    && pip install --no-index --no-deps --require-hashes --find-links /ctx/vendor/wheels -r /lab/py/requirements.lock \
    && rm -rf /ctx

WORKDIR /lab/py
USER lab
