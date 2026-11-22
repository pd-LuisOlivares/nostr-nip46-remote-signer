# B6, etapa 1: reproducibilidad desde un clon limpio

**Fecha:** 2026-11-21 · **Commit base:** `4b9e51eba698c3434f4fee3b0f6a5224e60e504b` (publicado en `origin/main`) · **Veredicto: PASS con observaciones**

> **Actualización B6.1A (2026-11-21):** las propuestas **P-35, P-36 y P-37** de este informe se resolvieron en [`phase-1.0B-B6.1A-local-auth.md`](phase-1.0B-B6.1A-local-auth.md) (P-37 en la interfaz; el hallazgo abierto en el backend es **P-38**). La observación de nombres fijos de Compose se corrigió de forma mínima (`APP_IMAGE`, `-p`). Las cifras de pruebas de este informe son anteriores a B6.1A.

Esta etapa comprueba que un tercero puede clonar, instalar, ejecutar y probar la aplicación siguiendo el `README.md`. **No** es una validación con Stacker News (no hubo conexión a Stacker News ni a relays públicos) y **no** prueba compatibilidad universal: es una ejecución en **un único equipo** (ver «Qué se ejecutó y qué solo se infiere»).

## 1. Estado inicial de Git

- Repositorio de trabajo: rama `main`, `HEAD` = `origin/main` = `4b9e51e`, árbol limpio (`git status -sb` → `## main...origin/main`).
- Clon limpio: `git clone <URL de origin>` (el remoto `origin` de este repositorio) en una carpeta nueva **fuera** del repositorio (`%TEMP%\b6-repro-20261121\clone`, se conserva hasta que el propietario decida borrarla). `HEAD` del clon = `4b9e51e`, sin `.env`, sin `lab/vendor/` ni `lab/results/`.

## 2. Entorno de prueba

| Elemento | Versión |
|---|---|
| Sistema | Windows 11 Pro (build 10.0.26300), x86_64 |
| Python | 3.12.10 (lanzador `py -3.12`); pip 25.0.1 dentro del venv |
| Git | 2.55.0.windows.5 |
| Docker | 25.0.2 (Docker Desktop), Compose v2.24.3-desktop.1 |
| Navegador de las E2E | Google Chrome 158.0.8127.36 (instalado en el equipo) vía Playwright 1.64.1 |
| Shell | PowerShell 7 |
| Python dentro de la imagen | 3.12.16 (el mismo que el digest D-6) |

Dependencias instaladas: idénticas a `constraints.txt` (fastapi 0.165.0, uvicorn 0.54.0, coincurve 21.0.0, cryptography 50.0.2, websockets 17.4, PyJWT 2.15.1, pytest 9.2.0, httpx 0.28.1, playwright 1.64.1, etc.).

## 3. Comandos ejecutados desde el clon limpio

```powershell
# Instalación: README §5 (literal)
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -c constraints.txt -e ".[dev]"
python -m pip check

# Pruebas: README §9 (literal), sin variables especiales
python -m pytest -q -rs

# Docker Compose: README §10 y §12 (literal; sin .env, sin PYTHON_IMAGE: etiqueta mutable por defecto)
docker compose up --build -d
docker compose ps
docker compose down

# Comprobaciones adicionales (scripts desechables fuera del repositorio, ver §7)
$env:NIP44_VECTORS_PATH = "<archivo de vectores del equipo original>"; python -m pytest tests/nostr/test_nip44.py -q
$env:E2E_DOCKER = "1"; python -m pytest tests/e2e/test_docker_ndk.py -v
$env:NIP44_VECTORS_PATH = "..."; $env:E2E_DOCKER = "1"; python -m pytest -q
```

## 4. Instalación: PASS

33 paquetes instalados sin errores (`EXIT=0`); `pip check`: «No broken requirements found». Las versiones coinciden con `constraints.txt`. No se necesitó ningún secreto ni archivo del equipo original.

## 5. Docker Compose: PASS

- `docker compose up --build -d`: construcción en 13 s (la capa `pip install -c constraints.txt .` **sí se ejecutó** y descargó de PyPI; las capas de usuario quedaron en caché), contenedor `healthy`.
- Puerto publicado solo en `127.0.0.1:8000->8000/tcp`. En el contenedor: usuario `uid=10001(app)`, `ReadonlyRootfs=true`, `CapDrop=[ALL]`, `no-new-privileges:true`.
- `GET /health` → 200 `{"status":"ok"}`. `GET /` (interfaz) → 200 con CSP estricta y `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`. `/docs` y `/openapi.json` → 404. `/api/status` sin sesión → 401. `Host` ajeno → 400.
- Código de acceso: aparece **una sola vez** en el registro de arranque; tras iniciar sesión y cerrarla, ni el código se repite ni hay JWT en el registro. Sin conexiones a relays (0 líneas de conexión en el registro).
- `docker compose down` dejó 0 contenedores y 0 redes del proyecto.
- **No se ejecutó** `--no-cache`: no se comprobó una construcción completamente en frío. La etiqueta mutable `python:3.12-slim` produjo una imagen con Python 3.12.16 (coherente con el digest D-6), lo cual **no** garantiza lo mismo en el futuro.

## 6. Pruebas: PASS

| Ejecución (en el clon) | Resultado |
|---|---|
| `python -m pytest -q -rs`, sin variables | **613 passed, 9 skipped**, 1 warning, 42 s |
| `tests/nostr/test_nip44.py` con `NIP44_VECTORS_PATH` apuntando al archivo del equipo original | 19 passed |
| `tests/e2e/test_docker_ndk.py` con `E2E_DOCKER=1` (NDK 2.12.2 real) | 1 passed (11 s) |
| Suite completa con vectores y `E2E_DOCKER=1` | **622 passed**, 1 warning, 51 s |

Las 9 omitidas de la ejecución limpia son: 8 vectores oficiales NIP-44 (no se versionan; faltan en `lab/vendor/`, comportamiento documentado en el README §9) y el E2E de Docker (requiere `E2E_DOCKER=1`). Las 7 E2E de navegador **sí** se ejecutaron (Chrome instalado). La ejecución completa coincide con la del equipo original (622).

**Dependencias del equipo original en estas pruebas:** el archivo de vectores NIP-44 y las imágenes de laboratorio `nip46-lab-py:1.0a` / `nip46-lab-node:1.0a` ya existían en el equipo; **no se reconstruyeron** desde cero (requeriría `lab/tools/fetch_artifacts.py`, descargas de npm, PyPI y GitHub fuera del alcance de esta etapa). Por tanto, la parte «E2E de Docker con NDK real» demuestra que la imagen del producto construida **desde el clon** funciona con el laboratorio, pero **no** que el laboratorio se pueda reconstruir en un equipo limpio (no verificado).

## 7. Interfaz local y flujo del operador: PASS

Chrome (Playwright, un script desechable fuera del repositorio) contra el **contenedor** Docker: **19/19** comprobaciones. Código incorrecto → error visible y sigue en el inicio de sesión; código correcto → panel; el campo del código se vacía; cookie `nip46_session` `HttpOnly`, `SameSite=Strict`, `Path=/api`; sin `localStorage` ni `sessionStorage`; JS no ve la cookie; «Crear identidad temporal» muestra una clave pública de 64 hex y ninguna `nsec` en la página; «Cerrar sesión» vuelve al inicio de sesión y elimina la cookie; sin violaciones de CSP ni errores de JS; ninguna petición fuera de `127.0.0.1:8000`. El firmante **no** se inició (sin relay).

Mediante la API con `Bearer`: código incorrecto → 401; correcto → token; `GET /api/auth/session`, `/api/status`, `POST /api/identity` y `/api/audit` → éxito; `POST /api/auth/logout` → 204 y el token revocado pasa a 401.

## 8. Problemas encontrados

| # | Hallazgo | Tipo | Estado |
|---|---|---|---|
| 1 | Un clon limpio da **613 passed, 9 skipped**, no «621 passed, 1 skipped» como indicaban el *handoff* y el cierre: la diferencia son 8 vectores oficiales NIP-44 que solo existen en el equipo original | Documentación | **Corregido** (README §9, *handoff* §4) |
| 2 | `compose.yaml` fija el nombre del proyecto y la imagen `nostr-nip46-remote-signer:dev`: otro clon reemplaza esa imagen y comparte contenedor/red con el repositorio original | Portabilidad (documentación) | **Documentado** (README §10) |
| 3 | **429 «Demasiados intentos»** al iniciar sesión justo después de levantar el contenedor. Causa observada en el registro de acceso: antes de cualquier petición mía llegaron 9 respuestas 401 con la forma exacta del sondeo de la UI (`status`, `requests`, `connections`, `audit`, por duplicado): una **pestaña antigua del navegador** (de B4) en `127.0.0.1:8000`, con cookie ya inválida. Cada petición sin credenciales válidas cuenta como fallo (umbral: más de 10 por minuto) y el inicio de sesión también se bloquea | Comportamiento de diseño con efecto de usabilidad | **Documentado** (README §8); propuesta P-35, **sin cambios de código** |
| 4 | Al cargar la UI sin sesión, `GET /api/auth/session` (la sonda normal) cuenta como fallo; una sesión caducada con la pestaña abierta suma 4 fallos por ciclo de sondeo | Diseño (relacionado con 3) | Propuesta P-35 |
| 5 | La UI desactiva «Aprobar» ante una comprobación en `false` (confirmado), pero el manejador no lo vuelve a comprobar: un evento `click` **sintético** de JavaScript sobre el botón desactivado sí llega a `decide()`. Clic real de ratón y teclado: no envían nada. El servidor sigue siendo la autoridad (nunca crea solicitudes pendientes que incumplan la política) | Endurecimiento (defensa en profundidad) | Propuesta P-37; **no implementado** (toca el flujo de aprobación) |
| 6 | `favicon.ico` → 404 (mensaje en la consola) | Cosmético | Sin acción |
| 7 | El laboratorio (imágenes `nip46-lab-*`) no se reconstruyó desde cero | Alcance | No verificado |
| 8 | `.gitignore` no protege archivos de identidad privada | Seguridad (proceso) | Propuesta P-36 (ver §10) |

Nota sobre el hallazgo 3: la explicación de la pestaña antigua se **infiere** del registro (forma y momento de las peticiones); no se identificó la pestaña. Tras cerrar todo y reiniciar el contenedor no volvieron a aparecer peticiones espontáneas (15 s de observación).

## 9. Correcciones aplicadas (solo documentación; ningún cambio de código ni de configuración)

- `README.md`: resultado esperado de la suite en un clon limpio (§9); nota de nombre de proyecto e imagen fijos en Compose (§10); solución al 429 por pestañas antiguas (§8).
- `docs/handoff-2026-11-21.md`: cifras de pruebas, estado de B6 y referencia a este documento.
- `docs/decisions.md`: sección de esta etapa; P-34 actualizada; P-35, P-36 y P-37 nuevas.
- `docs/ai-log.md`: interacción 33.
- Este archivo.

`AGENTS.md`, `CLAUDE.md`, `.gitignore` y el código no se modificaron. No hubo commit ni push.

## 10. Propuestas (requieren decisión del propietario)

**P-36, `.gitignore`.** Se probó en el clon descartable (no en el repositorio): ignora `identity.key` y variantes, no ignora ningún archivo ya versionado (`git ls-files -ci` → vacío) ni `.env.example` ni `lab/tools/b4_identity.py`:

```gitignore
# Identidad y claves privadas Nostr (nunca versionar). La identidad de pruebas B4 vive fuera del repositorio
# (~/.nip46-b4/identity.key); estas reglas protegen frente a copias accidentales dentro del árbol.
identity.key
*.nsec
*.key
*.pem
.nip46-b4/
# Variantes locales de configuración con valores reales (la plantilla .env.example SÍ se versiona)
.env.*
!.env.example
```

Justificación: hoy solo `.env` está excluido; una copia de `identity.key` (o de su respaldo) dentro del árbol aparecería como archivo nuevo sin ignorar. Antes de añadir `*.key`/`*.pem`, la comprobación sobre los 199 archivos versionados no encontró ninguno con esas extensiones. Riesgo: ocultaría a futuro un fixture legítimo con esas extensiones (se podría forzar con `git add -f`).

**P-35, contador de fallos.** No contar como fallo la ausencia de credenciales (la sonda `GET /api/auth/session` y el sondeo de una pestaña sin sesión) y solo contar credenciales presentes e inválidas, o no bloquear el inicio de sesión por fallos de otras rutas. Afecta al comportamiento de autenticación (D-8): **se consulta antes de implementar**.

**P-37, UI.** En `decide()`, ignorar `approve` si la tarjeta tiene alguna comprobación en `false` y añadir una prueba E2E (tarjeta manipulada servida con `page.route`, incluido HTML hostil, como la sonda de esta etapa). Afecta al flujo de aprobación: **se consulta antes de implementar**. Resultado de la sonda sobre la UI actual (Chrome, 11 de 12 comprobaciones; la 12.ª es el hallazgo 5): HTML hostil mostrado como texto literal, sin `<img>`/`<script>`, sin ejecución de JS; «Aprobar» desactivado con una comprobación en rojo; activo con las 11 en verde y en `connect`.

## 11. Qué se ejecutó y qué solo se infiere

- **Ejecutado (en un único equipo, Windows 11):** instalación, pruebas, Docker Compose, interfaz en Chrome 158 y las comprobaciones de las secciones 4 a 7.
- **Inferido, no ejecutado:** Linux y macOS (la imagen Docker corre en Linux amd64 y no hay código específico de Windows, pero no se probó el flujo del README fuera de Windows); equipos sin Chrome/Edge (por la lectura de `tests/e2e/conftest.py`, las E2E de navegador se omitirían con aviso, no fallarían); Firefox/Safari (P-34 pendiente); arquitectura arm64; una construcción de Docker en frío (`--no-cache`); la reconstrucción del laboratorio desde cero.
- **No ejecutado, por restricción:** cualquier conexión a Stacker News o a relays públicos; la identidad privada de B4 no se usó ni se leyó.

## 12. Riesgos pendientes

- La reproducibilidad está demostrada en **un** equipo; no equivale a compatibilidad universal.
- Sin *hashes* en `constraints.txt` y base de imagen por etiqueta mutable por defecto (ya documentado).
- Las 8 pruebas de vectores NIP-44 solo corren si el usuario obtiene el archivo (limitación de licencia ya documentada).
- El bloqueo por fallos puede impedir el inicio de sesión durante un minuto si hay pestañas antiguas abiertas (P-35).
- B6 real (validación con Stacker News repetida desde la interfaz) sigue **pendiente de autorización**.

## 13. Veredicto: **PASS con observaciones**

Se cumplen los criterios de aceptación: el clon se instala con el README, la aplicación arranca con Docker Compose, las pruebas terminan correctamente, la interfaz funciona, no se requirió ningún secreto del equipo original y las limitaciones de plataforma quedan explícitas. Observaciones: las cifras de la suite difieren de las del equipo original por 8 pruebas que dependen de un archivo no versionado (corregido en la documentación), y las propuestas P-35, P-36 y P-37 quedan a la espera de decisión.
