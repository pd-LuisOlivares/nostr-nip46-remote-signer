# Obtención y verificación de metadatos de dependencias (Fase 1.0A, paso 1)

| Campo | Valor |
|---|---|
| Fecha del prompt (UTC) | 2026-11-20T18:21:59.699Z |
| Fase | 1.0A |
| Agente | Claude Code (extensión de VS Code, versión 2.1.329) |
| Modelo | claude-sonnet-5-5 (campo `model` de los registros de sesión) |
| Nivel de razonamiento | high (campo `effort` de los registros de sesión) |
| Sesión | 35f0f3c1-13e9-47b9-832f-f6252cd2166f |
| Origen de la transcripción | Archivo de sesión local de Claude Code (JSONL), extraído con script; no reconstruido |
| Estado | Completa (contenido visible) |

**Qué contiene y qué no.** Prompt del propietario (sin las etiquetas `<pasted_content>` que añade el cliente) y todo el texto visible de las respuestas de Claude Code, en orden. Las llamadas a herramientas se indican con una línea de marcador; su contenido y sus salidas no se incluyen, porque los archivos resultantes están en el repositorio. **No se incluye razonamiento interno del modelo** ni contexto del sistema. Redacción aplicada: usuario local, nombre del autor y correos; la ruta absoluta del proyecto se acortó a ruta relativa. Las marcas `<!-- fecha -->` son del archivo de sesión.

---

## Prompt del propietario (2026-11-20T18:21:59.699Z)

# FASE 1.0A — Aprobación del diseño y autorización del paso 1

He revisado tu propuesta de dependencias y arquitectura del laboratorio.

Apruebo las siguientes decisiones:

1. **Opción A: Docker**, con red interna y sin puertos publicados.
2. **Nivel 1 y Nivel 2**, incluyendo NDK 2.12.2, firmante de referencia en Node y simulador Python.
3. **Experimento E7**, adicional a E1–E6, para errores, mensajes inválidos y correlación.
4. **Relay Nostr mínimo propio**, exclusivamente para el laboratorio.
5. **Modificación limitada de `.gitignore`** para excluir `lab/results/`, `lab/node/node_modules/` y otros artefactos generados estrictamente necesarios, justificando cada regla.
6. **Consulta de metadatos de dependencias**, incluyendo versiones, licencias, hashes, digests y avisos de seguridad relevantes.

## Alcance de la autorización actual

Autorizo exclusivamente el **paso 1: obtención y verificación de metadatos**.

Puedes consultar los registros oficiales de npm, PyPI y Docker Hub, así como fuentes oficiales necesarias para comprobar versiones, integridad, licencias y seguridad.

No autorizo todavía:

- `docker pull`.
- `docker build`.
- `npm ci` ni `npm install`.
- `pip install`.
- Descargar archivos ejecutables o paquetes.
- Ejecutar código de dependencias nuevas.
- Conectarse a relays públicos.
- Conectarse a Stacker News.
- Crear commits o hacer push.

No utilices comandos de descarga como mecanismo indirecto para ejecutar software.

## Verificaciones solicitadas

### 1. Dependencias Node

Confirma:

- NDK 2.12.2.
- `nostr-tools` 2.16.2.
- Resolución de las 44 dependencias del lockfile.
- Integridad SHA-512.
- Licencias faltantes.
- Scripts de instalación y su tratamiento.
- Compatibilidad con Node 22.

Identifica cualquier dependencia con vulnerabilidades relevantes conocidas.

### 2. Dependencias Python

Confirma:

- `coincurve` 21.0.0.
- `cryptography` 50.0.2.
- `websockets` 17.4.
- Versiones exactas y hashes de `cffi` y `pycparser`.
- Disponibilidad para Python 3.12 y la plataforma Linux del contenedor.
- Licencias y riesgos relevantes.

No modifiques las dependencias productivas del proyecto.

### 3. Imágenes Docker

Obtén y documenta los digests completos de las imágenes propuestas.

Comprueba la arquitectura de las imágenes y su compatibilidad con el equipo.

Evita etiquetas flotantes sin digest fijado.

### 4. Aislamiento

Presenta el diseño definitivo para:

- Descargas autorizadas durante la construcción.
- Ejecución experimental sin Internet.
- Red Docker `internal: true`.
- Ausencia de puertos publicados.
- Gestión de identidades desechables.
- Limpieza de contenedores y procesos.
- Protección de resultados y secretos.

Aclara cómo evitarás que la fase de construcción tenga acceso a redes o recursos no autorizados.

### 5. Relay mínimo

Define el subconjunto de NIP-01 necesario para los experimentos.

Incluye pruebas de:

- Suscripción.
- Publicación.
- Entrega de eventos.
- Filtrado.
- Confirmaciones.
- Manejo de conexiones.

No implementes funcionalidades ajenas al laboratorio.

### 6. Entrega

Presenta:

1. Tabla definitiva de dependencias.
2. Hashes y digests completos.
3. Licencias y vulnerabilidades identificadas.
4. Arquitectura definitiva del laboratorio.
5. Plan de descargas e instalación.
6. Orden propuesto para ejecutar los experimentos E1–E7.
7. Riesgos residuales.
8. Estado de Git.

No modifiques archivos del proyecto durante este paso, salvo que sea imprescindible para registrar la investigación y cuentes con autorización específica.

**Detente y espera mi aprobación antes de descargar imágenes, instalar dependencias o construir el laboratorio.**


## Respuesta de Claude Code

<!-- 2026-11-20T18:22:56.354Z -->
Autorización clara: solo **paso 1, metadatos** (npm, PyPI, Docker Hub y fuentes oficiales), sin descargar paquetes ni imágenes, sin tocar archivos del proyecto. Todo lo que obtenga va al scratchpad. Empiezo con comprobaciones locales de arquitectura y del constructor de Docker.

> *[Llamada a herramienta: PowerShell — Check local Docker architecture, builder and git state]*

> *[Llamada a herramienta: PowerShell — Query Docker Hub tag metadata for Node 22.23 images]*

<!-- 2026-11-20T18:23:18.291Z -->
`node:22.23.5-bookworm-slim` existe. Verifico su digest directamente en el registro (manifiestos con token anónimo, sin descargar capas) y busco el equivalente exacto de `python:3.12-slim`.

> *[Llamada a herramienta: PowerShell — Query Docker Hub tags for python 3.12 slim images]*

<!-- 2026-11-20T18:23:32.127Z -->
Verifico los digests contra el registro oficial (manifiestos; sin capas ni blobs de imagen).

> *[Llamada a herramienta: PowerShell — Verify image index digests and platforms against Docker registry manifests]*

<!-- 2026-11-20T18:23:44.655Z -->
Digests confirmados por dos vías y ambas imágenes tienen `linux/amd64`. Obtengo además el tamaño comprimido que implicaría la descarga (solo del manifiesto de la plataforma).

> *[Llamada a herramienta: PowerShell — Get amd64 manifest layer sizes for the two proposed images]*

<!-- 2026-11-20T18:23:55.337Z -->
Ahora la fuente oficial de Node.js: estado de la versión 22.23.5 (seguridad, LTS, fecha de fin de soporte).

> *[Llamada a herramienta: PowerShell — Check official Node.js release metadata for v22.23.5]*

<!-- 2026-11-20T18:24:08.101Z -->
Ahora npm: genero la lista exacta de la clausura (nombre, versión, ruta e integridad del lockfile) y consulto el documento de cada versión en `registry.npmjs.org` (solo JSON de metadatos).

> *[Llamada a herramienta: PowerShell — Compute npm closure list and fetch each version metadata document]*

<!-- 2026-11-20T18:24:44.547Z -->
Análisis de los 43 documentos de versión: integridad frente al lockfile, licencias, scripts de instalación, `engines`, obsolescencia y firmas del registro.

> *[Llamada a herramienta: PowerShell — Analyze npm metadata: integrity, licenses, scripts, engines, deprecations, signatures]*

> *[Llamada a herramienta: PowerShell — Verify npm registry ECDSA signatures with Node built-in crypto]*

<!-- 2026-11-20T18:25:09.980Z -->
44/44 firmas verificadas. Ahora los avisos de seguridad de npm (endpoint oficial de avisos por lote; solo se envían nombres y versiones públicas) y las licencias que faltaban en el lockfile.

> *[Llamada a herramienta: PowerShell — Query npm bulk advisories and list licenses missing from the lockfile]*

> *[Llamada a herramienta: PowerShell — Look up latest cffi and pycparser versions and constraints on PyPI]*

<!-- 2026-11-20T18:25:41.110Z -->
`cffi` 2.1.1 y `pycparser` 3.12 son compatibles con Python 3.12. Obtengo los metadatos oficiales por versión de los cinco paquetes.

> *[Llamada a herramienta: PowerShell — Fetch and summarize official PyPI metadata for the five level-2 packages]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: PowerShell — Check Node 22 built-in WebSocket global (local, no dependencies)]*

> *[Llamada a herramienta: PowerShell — Compute minimal runtime npm closure excluding websocket-polyfill]*

<!-- 2026-11-20T18:27:16.512Z -->
Genero la tabla completa de las 44 entradas con integridad completa y marca de la clausura mínima.

> *[Llamada a herramienta: PowerShell — Print the 44-entry npm table with full integrity hashes]*

<!-- 2026-11-20T18:27:39.558Z -->
Verifico que el paso 1 no modificó nada del proyecto ni dejó procesos o contenedores.

> *[Llamada a herramienta: PowerShell — Confirm step 1 left the repository, Docker and processes untouched]*

<!-- 2026-11-20T18:27:46.826Z -->
Hay un proceso `node` (PID 28328). Compruebo si es mío antes de afirmar nada.

> *[Llamada a herramienta: PowerShell — Inspect the running node process to determine who started it]*

<!-- 2026-11-20T18:29:07.471Z -->
Paso 1 completado: metadatos obtenidos y verificados. No descargué paquetes ni imágenes, no ejecuté código de dependencias, no toqué relays ni Stacker News, y no modifiqué ningún archivo del proyecto. La evidencia cruda quedó solo en el scratchpad de la sesión.

El proceso `node` (PID 28328) no es mío: es el runtime de OpenAI Codex, iniciado a las 11:40, anterior a esta fase.

## Resumen
- **npm:** 44/44 integridades sha512 coinciden con el lockfile de Stacker News. 44/44 firmas ECDSA verificadas con las claves públicas oficiales de npm. Cero avisos de seguridad en npm.
- **PyPI:** cero vulnerabilidades y ningún paquete retirado (*yanked*).
- **Node 22:** todas las dependencias son compatibles con Node 22.
- **Hallazgo de diseño:** NDK 2.12.2 **no importa** `websocket-polyfill` en su código ESM (`dist/index.mjs`) ni en el CommonJS. Node 22 trae `WebSocket` global (comprobado localmente, v22.14.0). Por eso propongo instalar una **clausura mínima de 24 entradas** en vez de 44.
- **Cambio frente a lo que propuse:** el relay mínimo pasa a **Python** con `websockets`, no a Node. El servidor `websocket` de npm exige módulos nativos (`bufferutil`, `utf-8-validate`) que no se pueden compilar con `--ignore-scripts`.

## 1. Tabla definitiva de dependencias

### Imágenes Docker
Confirmadas por la API de Hub y por el registro `registry-1.docker.io`. Ambas tienen `linux/amd64`, igual que tu servidor Docker.

| Imagen | Tamaño comprimido | Nota |
|---|---|---|
| `node:22.23.5-bookworm-slim` | 79,9 MB | Es la versión de `.node-version` de Stacker News (22.23.5). Es la última 22.x, LTS «Jod», con marca de seguridad del 2026-11-11 y soporte hasta 2027-04-30. |
| `python:3.12.16-slim-trixie` | 43,3 MB | Equivale a la etiqueta `3.12-slim` actual del proyecto, es decir, el mismo sistema base que la imagen del proyecto. |

### Node (npm, `registry.npmjs.org`)
Clausura mínima, 24 entradas, 23 pares únicos, **sin scripts de instalación**.

| Paquete | Licencia |
|---|---|
| `@nostr-dev-kit/ndk` 2.12.2 | MIT |
| `nostr-tools` 2.16.2 | Unlicense |
| `@noble/curves` 1.8.1, 1.2.0, 1.1.0 | MIT |
| `@noble/hashes` 1.7.1, 1.5.0, 1.3.2, 1.3.1, 1.3.3 | MIT |
| `@noble/ciphers` 0.5.3, `@noble/secp256k1` 2.1.0 | MIT |
| `@scure/base` 1.1.9 y 1.1.1, `@scure/bip32` 1.3.1, `@scure/bip39` 1.2.1 | MIT |
| `debug` 4.4.3, `ms` 2.1.3, `tseep` 1.3.1, `typescript-lru-cache` 2.0.0, `utf8-buffer` 1.0.0 | MIT |
| `light-bolt11-decoder` 3.2.0, `nostr-wasm` 0.1.0 | MIT |

### Python (`pypi.org` y `files.pythonhosted.org`)

| Paquete | Licencia | Rueda elegida |
|---|---|---|
| `coincurve` 21.0.0 | MIT OR Apache-2.0 | `cp312 manylinux_2_17_x86_64` |
| `cryptography` 50.0.2 | Apache-2.0 OR BSD-3 | `cp311-abi3 manylinux_2_34_x86_64` |
| `cffi` 2.1.1 | MIT-0 | `cp312 manylinux_2_17_x86_64` |
| `pycparser` 3.12 | BSD-3 | `py3-none-any` |
| `websockets` 17.4 | BSD-3 | `py3-none-any` (pura, sin binarios) |

Los cinco son compatibles con Python 3.12 y con `linux/amd64`. `cffi` y `pycparser` son las versiones que faltaban, con sus hashes más abajo.

Las pruebas Python usarán `unittest`, no `pytest`. Así no se añaden otros cinco paquetes.

## 2. Hashes y digests completos

**Docker**
```text
node:22.23.5-bookworm-slim   índice  sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee
                             amd64   sha256:47725aca53d3295ec2d3be8f62726599b3033cc262edc2c7e429909b3ac599fc
python:3.12.16-slim-trixie   índice  sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
                             amd64   sha256:05a994d2344eb364cc186910f4fc8786a38215f39f00d0acc25bff33a08f4177
```

**Python (sha256)**
```text
coincurve-21.0.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl  1b04778b75339c6e46deb9ae3bcfc2250fbe48d1324153e4310fc4996e135715
cryptography-50.0.2-cp311-abi3-manylinux_2_34_x86_64.whl                      9dab55f57c74c3cad24c323bacbbd04be4705ba6eb0d92e920b1fc4837ed5079
cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl         c1453022f490d2459a11819d83ad1d586e9ff65a12ac3e705ffebd46d3685dcf
pycparser-3.12-py3-none-any.whl                                               a076f3f489b39b43ed13563a1dafe42447445bec2e294154ec5c57fcdda4c85e
websockets-17.4-py3-none-any.whl                                              c6bd2c9781915592b209160d0f017d4c7c82ad53075e6b0c24d2a89299e7f9e9
```
Alternativa por si falla la compatibilidad de glibc: `cryptography-50.0.2-cp311-abi3-manylinux_2_28_x86_64.whl`, hash `4061c0079120205fb760c58acab6443e217307dcf05e3702cf970e0689972856`.

**npm (sha512), clausura mínima**
```text
@nostr-dev-kit/[REDACTADO:correo]   sha512-uvautgwbpk3AgddoFpew67/FiaV/zpKwwvSnjCvbE/tAdJBpUUS+VjWR5WfUnJvxTy/ZZpPW+X2TkwVFHhUdvA==
[REDACTADO:correo]          sha512-ZxH9EbSt5ypURZj2TGNJxZd0Omb5ag5KZSu8IyJMCdLyg2KKz+2GA0sP/cSawCQEkyviIN4eRT4G2gB/t9lMRw==
@noble/[REDACTADO:correo]         sha512-warwspo+UYUPep0Q+vtdVB4Ugn8GGQj8iyB3gnRWsztmUHTI3S1nhdiWNsPUGL0vud7JlRRk1XEu7Lq1KGTnMQ==
@noble/[REDACTADO:correo]         sha512-oYclrNgRaM9SsBUBVbb8M6DTV7ZHRTKugureoYEncY5c65HOmRzvSiTE3y5CYaPYJA/GVkrhXEoF0M3Ya9PMnw==
@noble/[REDACTADO:correo]         sha512-091oBExgENk/kGj3AZmtBDMpxQPDtxQABR2B9lb1JbVTs6ytdzZNwvhxQ4MWasRNEzlbEH8jCWFCwhF/Obj5AA==
@noble/[REDACTADO:correo]         sha512-B8XBPsn4vT/KJAGqDzbwztd+6Yte3P4V7iafm24bxgDe/mlRuK6xmWPuCNrKt2vDafZ8MfJLlchDG/vYafQEjQ==
@noble/[REDACTADO:correo]         sha512-1j6kQFb7QRru7eKN3ZDvRcP13rugwdxZqCjbiAVZfIJwgj2A65UmT4TgARXGlXgnRkORLTDTrO19ZErt7+QXgA==
@noble/[REDACTADO:correo]         sha512-V7/fPHgl+jsVPXqqeOzT8egNj2iBIVt+ECeMMG8TdcnTikP3oaBtUVqpT/gYCR68aEBJSF+XbYUxStjbFMqIIA==
@noble/[REDACTADO:correo]         sha512-MVC8EAQp7MvEcm30KWENFjgR+Mkmf+D189XJTkFIlwohU5hcBbn1ZkKq7KVTi2Hme3PMGF390DaL52beVrIihQ==
@noble/[REDACTADO:correo]         sha512-EbqwksQwz9xDRGfDST86whPBgM65E0OH/pCgqW0GBVzO22bNE+NuIbeTb714+IfSjU3aRk47EUvXIb5bTsenKA==
@noble/[REDACTADO:correo]        sha512-B0+6IIHiqEs3BPMT0hcRmHvEj2QHOLu+uwt+tqDDeVd0oyVzh7BPrDcPjRnV1PV/5LaknXJJQvOuRGR0zQJz+w==
@noble/[REDACTADO:correo]      sha512-XLEQQNdablO0XZOIniFQimiXsZDNwaYgL96dZwC54Q30imSbAOFf3NKtepc+cXyuZf5Q1HCgbqgZ2UFFuHVcEw==
@scure/[REDACTADO:correo]           sha512-8YKhl8GHiNI/pU2VMaofa2Tor7PJRAjwQLBBuilkJ9L5+13yVbC7JO/wS7piioAvPSwR3JKM1IJ/u4xQzbcXKg==
@scure/[REDACTADO:correo]           sha512-ZxOhsSyxYwLJj3pLZCefNitxsj093tb2vq90mp2txoYeBqbcjDjqFhyM8eUjq/uFm6zJ+mUuqxlS2FkuSY1MTA==
@scure/[REDACTADO:correo]          sha512-osvveYtyzdEVbt3OfwwXFr4P2iVBL5u1Q3q4ONBfDY/UpOuXmOlbgwc1xECEboY8wIays8Yt6onaWMUdUbfl0A==
@scure/[REDACTADO:correo]          sha512-Z3/Fsz1yr904dduJD0NpiyRHhRYHdcnyh73FZWiV+/qhWi83wNJ3NWolYqCEN+ZWsUz2TWwajJggcRE9r1zUYg==
[REDACTADO:correo]                 sha512-RGwwWnwQvkVfavKVt22FGLw+xYSdzARwm0ru6DhTVA3umU5hZc28V3kO4stgYryrTlLpuvgI9GiijltAjNbcqA==
[REDACTADO:correo]                    sha512-6FlzubTLZG3J2a/NVCAleEhjzq5oxgHyaCU9yYXvcLsvoVaHJq/s5xXI6/XXP6tz7R9xAOtHnSO/tXtF3WRTlA==
[REDACTADO:correo]  sha512-3QEofgiBOP4Ehs9BI+RkZdXZNtSys0nsJ6fyGeSiAGCBsMwHGUDS/JQlY/sTnWs91A2Nh0S9XXfA8Sy9g6QpuQ==
[REDACTADO:correo]            sha512-78BTryCLcLYv96ONU8Ws3Q1JzjlAt+43pWQhIl86xZmWeegYCNLPml7yQ+gG3vR6V5h4XGj+TxO+SS5dsThQIA==
[REDACTADO:correo]                 sha512-ZPtfk1tQnZVyr7BPtbJ93qaAh2lZuIOpTMjhrYa4XctT8xe7t4SAW9LIxrySDuYMsfNNayE51E/WNGrNVgVicQ==
[REDACTADO:correo]  sha512-Jp57Qyy8wXeMkdNuZiglE6v2Cypg13eDA1chHwDG6kq51X7gk4K7P7HaDdzZKCxkegXkVHNcPD0n5aW6OZH3aA==
[REDACTADO:correo]           sha512-ueuhzvWnp5JU5CiGSY4WdKbiN/PO2AZ/lpeLiz2l38qwdLy/cW40XobgyuIWucNyum0B33bVB0owjFCeGBSLqg==
```

**Las otras 20 entradas del lockfile (excluidas, también verificadas contra el registro)**
```text
[REDACTADO:correo]    sha512-pF3kR8Uaoau78MpUmFfzbIRxXj9PeQrCuPepGE6JIsfsJ/o/iXr07Q2iQNzKSSblQJ0FiGWlS64N4pVSm+O3Dg==
[REDACTADO:correo]                 sha512-+O2ybLVLKcBwKm4HymCEwZIT0PpwS3gCYnxfSDEjJEKADvIFruaQjd3m7CAKNU1c7N3X3WjVz87re7TA2A5FUw==
[REDACTADO:correo]            sha512-/REy6amwPZl44DDzvRCkaI1q1bIiQB0mEFQLUrhz3z2EK91cp3n72rAjUlrTP0zV22HJIUOVHQGPxhFRjxjt+Q==
[REDACTADO:correo]            sha512-4T53u4PdgsXqKaIctwF8ifXlRTTmEPJ8iEPWFdGZvcf7sbwYo6FKFEX9eNNAnzFZ7EzJAQ3CJeOtCRA4rDp7Pw==
[REDACTADO:correo]        sha512-NTZVKn9IylLwUzaKjkas1e4u2DLNcV4rdYagA4PWdPwW87Bi7z+BznyKSRwS/761tV/lzCGXplWsiaMjLqP2zQ==
[REDACTADO:correo]                 sha512-bC7ElrdJaJnPbAP+1EotYvqZsb3ecl5wi6Bfi6BJTUcNowp6cvspg0jXznRTKDjm/E7AdgFBVeAPVMNcKGsHMA==
[REDACTADO:correo]                    sha512-Tpp60P6IUJDTuOq/5Z8cdskzJujfwqfOTkrwIwj7IRISpnkJnT6SyJ4PCPnGMoFjC9ddhal5KVIYtAt97ix05A==
[REDACTADO:correo]             sha512-p2snDhiLaXe6dahss1LddxqEm+SkuDvV8dnIQG0MWjyHpcMNfXKPE+/Cc0y+PhxJX3A4xGNeFCj5oc0BUh6deg==
[REDACTADO:correo]          sha512-zw4SRzoUkd+cl+ZoE15A9o1oQd920Bb0iOJMQkQhl3jNc03YqVjAhG7scf9C5KWRU/R13Orf588uCC6525o02g==
[REDACTADO:correo]                     sha512-MOqHvMWF9/9MX6nza0KgvFH4HpMU0EF5uUDXqX/BtxtU8NfB0QzRtJ8Oe/6SuS4kbhyzVJwjd97EA4PKrzJ8bw==
[REDACTADO:correo]                  sha512-8j+1QmAbPvLZow5Qpi6NCaN8FB60p/6x8/vfNqOk/hC+HuvFZhL4+WfekuhQLiqFZXOgQdrs3B+XxEmCc6b3FQ==
[REDACTADO:correo]            sha512-U9bFFjX8tFiATgtkJ1zg25+KviIXpgRvRHS8sau3GfhVzThRQrOeksPeT0BWW2MNZs1OEWJ1DPXOQMn0KKRkvg==
[REDACTADO:correo]                   sha512-6hxeJYaL110a9b5TEJSj0gojyHQAmA2ch5Os+ySCiA1QGdS697XWY1pzsrSjqA9LDEEgdB/KypIlR59RcLuHYw==
[REDACTADO:correo]                sha512-kTUIGKQ/mDPFoJ0oVfcmyJn4iBDRptjNVIzwIFR7tqWXdVI9xfA2RMwY/gbSpJG3lkdWNEjLap/NqVHZiJsdfg==
[REDACTADO:correo]         sha512-D9rRn9y7kLPnJ+hMq7S/nhvoKwwvVJahBi2BPmx3bvbsEdK3W9ii8cBSGjP+72/LnM4n6fo3+dkCX5FeTQruXA==
[REDACTADO:correo]             sha512-CXdUiJembsNjuToQvxayPZF9Vqht7hewsvy2sOWafLvi2awflj9mOC6bHIg50orX8IJvWKY9wYQ/zB2kogPslQ==
[REDACTADO:correo]  sha512-zdu8XMNEDepKKR+XYOXAVPtWui0ly0NtohUscw+UmaHiAWT8hrV1rr//H6V+0DvJ3OQ19S979M0laLfX8rm82Q==
[REDACTADO:correo]         sha512-cyA56iCMHAh5CdzjJIa4aohJyeO1YbwLi3Jc35MmRU6poroFjIGZzUzupGiRPOjgHg9TLu43xbpwXk523fMxKA==
[REDACTADO:correo]       sha512-Z6czzLq4u8fPOyx7TU6X3dvUZVvoJmxSQ+IcrlmagKhilxlhZgxPK6C5Jqbkw1IDUmFTM+cz9QDnnLTwDz/2gQ==
[REDACTADO:correo]                 sha512-MvQa//+KcZCUkBTIC9blM+CU9J2GzuTytsOUwf2lidtvkx/6gnEp1QvJv34t9vdjhFmha/mUiNDbN0D0mJWdug==
```

## 3. Licencias y vulnerabilidades
- **Licencias:** las 11 que el lockfile no declaraba existen en el registro. Diez son MIT y `websocket-polyfill` es BSD-3-Clause. Toda la clausura es permisiva.
- **Avisos de seguridad:** el servicio oficial de avisos de npm (consultado con 34 nombres de paquete de 43 versiones únicas) devolvió `{}`, sin avisos. El campo `vulnerabilities` de PyPI está vacío para los cinco paquetes.
- **Scripts de instalación:** solo `bufferutil`, `utf-8-validate` y `es5-ext`, los tres de la parte excluida.
  - `bufferutil` y `utf-8-validate` ejecutan `node-gyp-build`.
  - `es5-ext` ejecuta un `postinstall` que corre `_postinstall.js`, que no revisé.
  - Con la clausura mínima ninguno se instala.
- **Obsoleto:** `yaeti` 0.0.6, también excluido.
- **No evaluado:** las imágenes Docker. No se pueden escanear sin descargarlas, así que sus vulnerabilidades quedan sin comprobar. Mitigación: Node es la última 22.x con marca de seguridad y Python es el último parche 3.12.
- **Fuentes de avisos:** solo los endpoints oficiales de npm y PyPI. No usé OSV como contraste.

## 4. Arquitectura definitiva (todo en Docker, proyecto `nip46-lab`)
```text
red nip46-lab  (internal: true, sin puertos publicados, sin ruta a Internet)
 ├─ relay        Python + websockets: NIP-01 mínimo, registra tramas (hash del contenido)
 ├─ client       Node 22 + NDK 2.12.2 real + arnés de instrumentación
 ├─ signer-ref   Node + nostr-tools (firmante de referencia: aísla el comportamiento de NDK)
 ├─ signer-py    Python + coincurve/cryptography (simulador: NIP-04 y NIP-44 propios)
 └─ runner       orquesta E1-E7 y escribe lab/results/*.jsonl (único bind mount, escritura)
```
- **Sin Internet en ejecución:** `internal: true`. Lo compruebo sin intentar conectar: `docker network inspect` y la tabla de rutas dentro del contenedor, que no debe tener ruta por defecto.
- **Endurecimiento:** `cap_drop: ALL`, `read_only`, `no-new-privileges`, usuario no root, `tmpfs` para escrituras y sin volúmenes salvo `lab/results`.
- **Identidades desechables:** se generan **en memoria** al arrancar cada contenedor, nunca a disco, por entorno ni por argumento de línea de comandos.
- **Resultados:** los registros llevan claves públicas truncadas, ids de evento, esquema, tiempos y hash del texto plano. Nunca claves privadas, secretos de conexión ni texto descifrado. Al final escaneo `lab/results/` en busca de patrones de claves.
- **Limpieza:** `docker compose -p nip46-lab down -v --remove-orphans`. Después compruebo que `docker ps -a` queda vacío y que no queda la red del laboratorio. No toco `magento246_default` ni nada ajeno.

## 5. Plan de descargas e instalación (paso 2, solo con tu aprobación)
La construcción **no tiene Internet**, porque separo descargar de construir:
1. **Descargar y verificar, sin ejecutar nada.**
   - Un script mío, que te presentaré antes de usarlo, solo acepta HTTPS contra `registry.npmjs.org` y `files.pythonhosted.org`.
   - No sigue redirecciones a otros hosts y verifica sha512 o sha256 contra esta tabla antes de guardar nada en `lab/vendor/`.
   - Descarga 24 tarballs npm (el de NDK pesa 471 722 bytes) y 5 ruedas Python (≈6,7 MB).
2. **`docker pull` de las dos imágenes por digest** (≈123 MB). Es la única operación de red que no puedo filtrar por host; la acota el digest fijado.
3. **`docker build --network=none --pull=false`.**
   - Instala solo desde `lab/vendor/`.
   - Node: verifico sha512 de nuevo y extraigo con `tar`, sin `npm`. No uso `npm ci` porque exigiría `websocket-polyfill`.
   - Python: `pip install --no-index --no-deps --require-hashes`. Las ruedas no ejecutan código al instalarse.
   - Ningún `RUN` toca la red.
4. **Ejecución** en la red `internal`.

**`.gitignore`, tres reglas con su motivo:**
- `lab/results/`: salidas de ejecución, no deben versionarse; las conclusiones van a `docs/`.
- `lab/node/node_modules/`: dependencias instaladas, reproducibles desde los hashes versionados.
- `lab/vendor/`: artefactos descargados (binarios), verificables por hash.

## 6. Relay mínimo: subconjunto de NIP-01
- **Mensajes:** `EVENT`, `REQ` y `CLOSE` del cliente; `EVENT`, `OK`, `EOSE`, `CLOSED` y `NOTICE` del relay.
- **Filtros:** `ids`, `authors`, `kinds`, `#p` y `#e`, más `since` y `until`. No almacena eventos, así que `limit` se ignora y responde `EOSE` de inmediato.
- **Validación:** recalcula el `id` y verifica la firma Schnorr; si falla responde `OK false` con prefijo `invalid:`.
- **Duplicados:** los detecta con un caché acotado.
- **Límites:** 20 suscripciones por conexión y mensajes de hasta 64 KiB.
- **Fuera de alcance:** NIP-42, NIP-11, almacenamiento y límites de tasa.
- **Pruebas con `unittest`:** suscripción con `EOSE`; publicación con `OK`; entrega a dos suscriptores; filtrado positivo y negativo por `kinds`, `#p`, `authors`, `since` y `until`; `OK false` por `id` o firma inválidos; JSON malformado y mensajes desconocidos con `NOTICE`; duplicado; `CLOSE`; limpieza al desconectar; orden de entrega; exceso de tamaño.

## 7. Orden propuesto de ejecución
0. **Prerrequisitos:** pruebas del relay; vectores de NIP-44 para la implementación Python (tienen licencia sin confirmar). Si apruebas, bajaría esos vectores como dato local sin versionar.
1. **E1**, con el firmante de referencia: respuesta NIP-44 al `connect` NIP-04.
2. **E4**, con el firmante de referencia: modo espejo.
3. **E2**, con el firmante de referencia: `sign_event` `27235` y esquema de las solicitudes siguientes.
4. **E6**: respuestas rápidas consecutivas.
5. **E7** (propuesta): respuesta con `id` ajeno; con `error`; JSON malformado; cifrado indescifrable; MAC inválido; remitente distinto del firmante; respuesta duplicada; `auth_url` seguido de la respuesta final; `get_public_key` con `error`.
6. **E3**: Python descifra el primer `connect` NIP-04 de NDK.
7. **E5**: NIP-44 cruzado entre `nostr-tools` y Python, con 1, 32, 33, 1000 bytes y Unicode.
8. **Repetir E1, E2, E4, E6 y E7 con el simulador Python.**

**Regla de decisión, fijada antes de ejecutar:** se aplica sobre las corridas con el **simulador Python**, porque es lo que vamos a construir. Las corridas del firmante de referencia sirven para aislar causas.
- Si el de referencia pasa y el Python falla, el defecto es de nuestra criptografía. Eso se marca **INCONCLUSIVE** para la regla, se corrige y se repite.
- Se aplica exactamente la regla de la Fase 0.3: NIP-44 si E1 y E2 pasan; espejo si fallan pero E4 pasa; bloqueo si ambos fallan.

## 8. Riesgos residuales
- NDK correrá en **Node**, no en el navegador de Stacker News. Eso no demuestra compatibilidad real con Stacker News.
- El relay mínimo no reproduce NIP-42 ni límites de relays públicos.
- Las imágenes Docker no están escaneadas.
- El `cryptography` 50.0.2 no tiene avisos en PyPI, pero no revisé su historial.
- `cffi` 2.1.1 y `pycparser` 3.12 son versiones muy recientes (agosto y octubre de 2026).
- Una de las dos claves públicas de npm tiene fecha de expiración pasada (2025-01-29). Las 44 firmas verificaron igualmente, pero no determiné con cuál de las dos claves.
- La clausura mínima se aparta de lo que declara el `package.json` de NDK. La justifica que el `dist` publicado no la usa, pero hay que reflejarlo en el informe.

## 9. Estado de Git
- Árbol limpio, 0 cambios, commit `ec739bd` presente, y no hubo consultas al remoto.
- Docker sin contenedores ni imágenes nuevas.

## Lo que necesito para el paso 2
1. Aprobar la **clausura mínima** (24) en lugar de las 44.
2. Aprobar el **relay en Python** y la prueba con `unittest`.
3. Aprobar las **descargas** (24 tarballs, 5 ruedas y las 2 imágenes por digest) y la regla del script con lista de hosts permitidos.
4. Aprobar la **modificación de `.gitignore`** con esas tres reglas.
5. Decidir si descargo los **vectores NIP-44** como dato local sin versionar.
6. Aprobar el **orden de experimentos** y la **regla de decisión**.

Me detengo hasta que lo apruebes.
