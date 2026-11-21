# Imagen Node del laboratorio. Base fijada por digest (node:22.23.5-bookworm-slim, linux/amd64).
# Se construye con `network: none` (compose.yaml): instala SOLO desde lab/vendor/ ya verificado.
# Un unico COPY: varios COPY desde subcarpetas disparan un fallo de contexto de BuildKit en Windows.
FROM node@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee

ENV NODE_ENV=production \
    NO_UPDATE_NOTIFIER=1 \
    NODE_NO_WARNINGS=1

COPY . /ctx
RUN mkdir -p /lab/vendor && mv /ctx/node /lab/node && mv /ctx/deps /lab/deps && mv /ctx/vendor/npm /lab/vendor/npm \
    && rm -rf /ctx \
    && cd /lab/node && node install-vendor.mjs && rm -rf /lab/vendor

WORKDIR /lab/node
USER node
