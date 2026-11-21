# Laboratorio de interoperabilidad NIP-46 / NDK 2.12.2 (Fase 1.0A)

Laboratorio **aislado y desechable** para comprobar de forma experimental qué combinaciones de cifrado (NIP-04 / NIP-44) funcionan con el
cliente real que usa Stacker News (NDK 2.12.2) al hablar NIP-46 a través de un relay local. **No es el firmante productivo**, no toca `app/`
y no valida compatibilidad con Stacker News: solo con la versión de NDK examinada, ejecutándose en Node 22 (no en un navegador).

Resultados y conclusiones: [`docs/nip46-lab-report.md`](../docs/nip46-lab-report.md). Definiciones y criterios de los experimentos:
[`experiments/definitions.md`](experiments/definitions.md).

## Arquitectura

```text
red Docker `nip46-lab_lab_net` (internal: true → sin Internet y sin puertos publicados)
 ├─ relay        Python + websockets 17.4. Relay NIP-01 mínimo (EVENT/REQ/CLOSE, OK/EOSE/CLOSED/NOTICE). Verifica id y firma.
 ├─ signer-ref   Node + nostr-tools 2.16.2. Firmante de REFERENCIA (aísla el comportamiento de NDK).
 ├─ signer-py    Python + coincurve/cryptography. Simulador del firmante con NIP-04/NIP-44 propios.
 ├─ client       Node + NDK 2.12.2 REAL. Replica el parche de URL, el evento y las comprobaciones de servidor de Stacker News.
 ├─ py-job / node-job   Tareas puntuales (pruebas unittest, E5).
 └─ volumen `ctl` (tmpfs, en memoria): el firmante deja la URI bunker:// y la clave pública de identidad; nunca claves privadas.
```

- **Claves**: todas desechables, generadas en memoria al arrancar cada contenedor (E5 usa las claves públicas de juguete de los vectores
  oficiales). No se guardan ni se registran claves privadas ni secretos de conexión ni texto descifrado (solo su SHA-256).
- **Coordinación**: el firmante publica `ready` (y escribe `/ctl`) solo después de recibir el `EOSE` de su suscripción; el cliente espera ese
  archivo. NDK espera su propio `EOSE` antes de enviar. Así no hay solicitudes ni respuestas publicadas antes de que exista la suscripción
  (el relay no almacena eventos).
- **Endurecimiento** (todos los servicios): usuario no root, FS de solo lectura, `cap_drop: ALL`, `no-new-privileges`, `tmpfs` en `/tmp`,
  límites de memoria y procesos. La **construcción** usa `network: none`.

## Dependencias (manifiesto con hashes)

`deps/artifacts.json` fija cada artefacto con su hash: 24 entradas npm (23 tarballs únicos, clausura mínima de NDK 2.12.2 y
`nostr-tools` 2.16.2, sin scripts de instalación), 5 ruedas Python, los vectores NIP-44 y los digests de las dos imágenes base
(`node:22.23.5-bookworm-slim`, `python:3.12.16-slim-trixie`, ambas `linux/amd64`). `py/requirements.lock` exige `--require-hashes`.

## Reproducción (Windows/PowerShell; requiere Docker)

```powershell
# 1) Descargar y verificar artefactos (solo HTTPS, hosts del manifiesto, hash verificado antes de guardar; no ejecuta nada)
.\.venv\Scripts\python.exe lab\tools\fetch_artifacts.py

# 2) Descargar las dos imágenes base POR DIGEST
docker pull node@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee
docker pull python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# 3) Construir SIN red (instala solo desde lab/vendor/ con hashes)
docker compose -f lab/compose.yaml build relay signer-ref

# 4) Ejecutar (todo, o por etapas: units | isolation | ref | py | e5)
.\.venv\Scripts\python.exe lab\run_lab.py --stage all

# 5) Limpieza exclusiva del proyecto del laboratorio
docker compose -f lab/compose.yaml -p nip46-lab down -v --remove-orphans
```

Los resultados crudos van a `lab/results/` (excluido de Git). Los vectores NIP-44 (`lab/vendor/vectors/`) son un **dato local sin versionar**:
el repositorio de origen no declara licencia.

## Regresión del firmante del producto (B2)

`lab/run_product_regression.py` ejecuta el firmante **del producto** (`app/services`, imagen `nostr-nip46-remote-signer:dev`) frente al cliente NDK 2.12.2 real
y el relay del laboratorio, en una red Docker `internal` (sin Internet ni puertos publicados). Cubre E1, E2, E3 y E8 con criterios fijados en el propio script.
`lab/product/runner.py` **automatiza la aprobación del operador** y por eso se niega a arrancar si el relay no es `ws://relay:7777` o el origen no termina en `.invalid`:
es una diferencia exclusiva del arnés (el producto exige una decisión humana por la API). Requisitos: imágenes `nip46-lab-py:1.0a` y `nip46-lab-node:1.0a` y la imagen del producto
(`docker compose build`, mejor con `PYTHON_IMAGE=<digest>`). Resultados en `lab/results/product-regression-<fecha>/` (excluido de Git).

```powershell
.\.venv\Scripts\python.exe lab\run_product_regression.py          # servicio del producto
.\.venv\Scripts\python.exe lab\run_product_regression.py --api    # aplicación completa (Uvicorn + API HTTP con JWT), P-33
```

El modo `--api` levanta el servicio `app` (Uvicorn) en la red interna; `lab/product/driver.py` se ejecuta dentro del contenedor, canjea el código de acceso (leído del registro del contenedor) por un JWT y opera la API HTTP como lo haría el operador (aprobación por guion, solo en el arnés).

`lab/e2e/compose.yaml` es el escenario del E2E de navegador en Docker (`E2E_DOCKER=1 python -m pytest tests/e2e/test_docker_ndk.py`): producto publicado solo en `127.0.0.1`, relay del laboratorio y cliente NDK real; el producto solo conoce `ws://relay:7777`.

## Alcance y límites

- Relay mínimo: sin persistencia, NIP-42, NIP-11 ni límites de tasa.
- NDK corre en **Node 22**, no en el navegador de Stacker News; el comportamiento del bundle de producción no se ha observado.
- El simulador Python y el firmante de referencia implementan solo lo que NDK usa; no son el firmante definitivo.
- Límite **provisional** de NIP-44 en el laboratorio: 65535 bytes (propuesta P-14), no una regla de la especificación.
