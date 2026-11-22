# NIGHTLY REVIEW — revisión autónoma del 2026-11-22

Trabajo realizado sin supervisión, dentro de los límites autorizados: **sin modificar código funcional**, sin tocar el entorno B6.2 (contenedor, volumen y SQLite), sin conexiones a relays ni a Stacker News y **sin push**. Este informe no contiene credenciales ni secretos. Todo lo que no se ejecutó figura como «no verificado».

## 1. Resumen ejecutivo

| Área | Resultado |
|---|---|
| Clon limpio (Fase 1) | **PASS** para el estado publicado `70b4481`: instalación según el README, `1029 passed, 35 skipped, 0 failed` y stack Docker del perfil demo funcional. **No** cubre el flujo con Stacker News |
| Seguridad (Fase 2) | **Sin hallazgos críticos ni altos.** Historia de Git (9 commits) sin secretos reales. 2 hallazgos medios, varios bajos e informativos (§4) |
| Documentación (Fase 3) | URL real en el README, requisitos para el evaluador, PASS real documentado con lo confirmado frente a lo no respaldado, resultado de clon limpio |
| Arquitectura 8000/8001 (Fase 4) | Diagnosticada; **propuesta sin implementar** (§6). Hallazgo: el cliente de laboratorio y el perfil demo compiten por el puerto 8000 |
| Trazabilidad (Fase 5) | Transcripciones 50 a 52 **PARCIALES** (sesión abierta); `check` ejecutado (§11) |
| B6.2 | **Intacto**: mismo contenedor, mismo arranque, 0 reinicios, base con el mismo resumen lógico antes y después |

## 2. Validación del clon limpio (Fase 1): **PASS**

Clon desde `https://github.com/pd-LuisOlivares/nostr-nip46-remote-signer.git` (URL obtenida de `git remote -v`, sin modificar el remoto), `HEAD 70b4481`, 278 archivos versionados, árbol sin cambios, en `%TEMP%\nip46-cleanclone-test` (eliminado al terminar).

| Paso (según README) | Resultado |
|---|---|
| §5 `py -3.12 -m venv .venv` + `pip install -c constraints.txt -e ".[dev]"` | OK (Python 3.12.10) |
| `pip check` | «No broken requirements found» |
| §9 `python -m pytest -rs` | **1029 passed, 35 skipped, 0 failed** (2 min 14 s). Omitidas: 26 de Docker (`E2E_DOCKER` sin definir), **8 vectores oficiales NIP-44** (no se versionan: `lab/vendor/` está ignorado) y 1 de permisos POSIX. Las E2E de navegador (Chrome) se ejecutaron y pasan |
| Docker del perfil demo (`--env-file deploy/demo.env up --build -d`) con **proyecto `nip46-clonetest`, puerto 18090 y etiqueta `nip46-clonetest:eval`** (sin usar 8000 ni 8001 ni volúmenes existentes) | Construcción y arranque OK (13 s con capas en caché). Una **segunda construcción sin caché** (`build --no-cache`): OK; solo se instalaron las versiones de `constraints.txt` (PyPI real) |
| Comportamiento del contenedor | `healthy`; `GET /health` 200; interfaz servida con CSP, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, CORP y `Permissions-Policy`; API sin credenciales 401; **login con las credenciales del README 200 y contraseña incorrecta 401**; identidad temporal creada (201) **sin claves privadas en la respuesta**; cierre de sesión 204; modo `continuous`, relay `wss://relay.primal.net`, `allow_insecure` falso; `Host` ajeno 400; sin cabecera CORS para un origen ajeno; solo lectura, `cap_drop ALL`, `no-new-privileges`, usuario `app`, puerto solo en `127.0.0.1`; `admin_bootstrap result=created`; contraseña ausente de los registros; **0 sockets salientes y 0 eventos de relay/sesión/bunker** (el firmante no se inició) |
| Limpieza | Solo recursos con la etiqueta `nip46-clonetest` (verificada): contenedor, volumen `nip46-clonetest_app_data`, red, dos imágenes propias y el directorio temporal. `down -v` solo de ese proyecto |
| B6.2 después | Contenedor `c84dd353f674…` igual, arranque 04:47:20 UTC, 0 reinicios, `healthy`; base con el mismo resumen lógico (`431d7d3d…`, 1 administrador) |

**Limitaciones de esta verificación:** (a) la imagen base `python:3.12-slim` no estaba como etiqueta local y BuildKit la resolvió sin dejar una imagen nueva visible; no se midió la descarga desde cero de esa base; (b) el build usa la etiqueta mutable de la imagen base (D-6): otro día podría resolver a otra versión; (c) no se ejecutaron las pruebas de Docker (`E2E_DOCKER=1`) en el clon porque requieren las imágenes de laboratorio; (d) **no se probó el flujo con Stacker News**.

## 3. Pruebas ejecutadas en esta jornada

| Prueba | Resultado |
|---|---|
| Clon limpio completo (§2) | 1029 passed, 35 skipped, 0 failed |
| `tests/test_deploy_profile.py` tras editar README y decisiones | 24 passed |
| Árbol principal: suite completa, trazabilidad y `git diff --check` antes del commit local | ver §11 |

No se ejecutaron pruebas contra el contenedor B6.2 ni contra relays públicos.

## 4. Hallazgos de seguridad por criticidad (revisión estática)

**Crítico: ninguno. Alto: ninguno.**

### Medio
| # | Hallazgo | Recomendación |
|---|---|---|
| M-1 | **Correo de autoría en la historia pública.** Las dos identidades de autoría de los commits usan un correo de dominio corporativo del propietario; quedará visible en GitHub. Reescribir la historia **no** está autorizado | El propietario decide si lo acepta o si prefiere un correo `noreply` de GitHub para los commits futuros (`git config user.email`). Si se quisiera retirar del pasado, exige reescribir historia (decisión explícita) |
| M-2 | **El firmante B6.2 probablemente sigue iniciado con la identidad B4 en memoria** (se observó una conexión saliente abierta tras la prueba) y la contraseña de `b62-admin` quedó en el historial local de la sesión (fuera del repositorio) | Detener el firmante desde la interfaz, **cambiar la contraseña de `b62-admin`** y capturar antes la auditoría si interesa (se pierde al reiniciar) |

### Bajo
| # | Hallazgo | Recomendación |
|---|---|---|
| B-1 | **Credencial de demostración pública** en `deploy/demo.env` (D-18). Mitigada: puerto solo en `127.0.0.1`, comprobación de `Host`/`Origin`, `SameSite=Strict`, límite de 5 intentos, aprobación humana de cada `connect` y `sign_event` | Mantener los avisos; no ampliar el puerto. Confirmar que el propietario acepta publicarla |
| B-2 | **Dependencias sin hashes** y base `python:3.12-slim` mutable (D-6) | Activar el digest de la base y generar `constraints` con hashes cuando se apruebe; no implementado |
| B-3 | **Sin escáner automático de secretos** en el flujo de commits (la política prohíbe hooks de Git en este proyecto) | Ejecutar `tools/ai_sessions.py scan` y una revisión de secretos antes de cada commit/push; valorar un escáner en CI (decisión nueva) |
| B-4 | **Límite global de inicios de sesión** (5 fallos por 5 min, P-40): alguien con acceso local puede bloquear el ingreso | Riesgo aceptado y documentado en el README |
| B-5 | **Uvicorn escucha en `0.0.0.0` dentro del contenedor** (necesario para Docker). Solo `ports: 127.0.0.1:…` lo limita | No cambiar el mapeo de puertos de `compose.yaml`; el README ya lo advierte |
| B-6 | `Cache-Control` ausente en la página estática `/` (no contiene datos sensibles; las respuestas con secretos usan `no-store`) | Opcional: `no-cache` para la interfaz |
| B-7 | **`Origin` ausente se acepta** en el login (clientes que no son navegador); con `return_token` un proceso local puede obtener un JWT si conoce la contraseña | Diseño intencionado (CLI); con credencial pública es irrelevante en local. Sin acción |
| B-8 | **Transcripciones de IA publicadas** (55 en `docs/ai-sessions/`): redactadas y escaneadas, sin secretos; revelan el trabajo interno, rutas redactadas y la clave **pública** de B4 | El propietario decide si publicarlas tal cual; no cambian la seguridad |

### Informativo (verificado, sin acción)
- **Historia de Git, 9 commits, todas las líneas añadidas:** sin `nsec`, bloques de clave privada, JWT, cookies, tokens ni hashes Argon2id reales. Coincidencias revisadas con valores enmascarados: fixtures de `nostr-tools`, el ejemplo oficial de NIP-19, un JWT de juguete en una prueba de fugas, bytes `ab`×32 y un hash de juguete («sin valor real»). Ni la contraseña de `b62-admin` ni la de B6.2 aparecen.
- **`.gitignore`:** excluye `.env`, `.env.*`, `*.db` y sus auxiliares, `*.key`, `*.pem`, `identity.key`, `secrets/`, `lab/results/`, `lab/vendor/`, `*.log`, `.venv`. Versionados con nombre sensible, todos revisados: `deploy/*.env` (sin secretos salvo la credencial pública del perfil demo), `app/storage/secret_file.py` y `lab/tools/b4_identity.py` (código, sin claves).
- **JWT y CSRF** (revisión del código, sin cambios): HS256 fijado (`algorithms=[HS256]`, nunca `none`), claims obligatorios (`exp`, `iat`, `nbf`, `iss`, `aud`, `sub`, `jti`, `csrf`), `leeway=0`, revocación por `jti`, 8 sesiones como máximo, clave aleatoria solo en memoria; comparación CSRF con `secrets.compare_digest`; cookie `HttpOnly`, `SameSite=Strict`, `path=/api`, `Secure` configurable; `Host` y `Origin` locales exigidos.
- **Persistencia de administradores:** un único administrador con hash Argon2id; sin contraseñas, claves Nostr, JWT ni cookies en SQLite; SQL parametrizado solo en `app/storage/`; archivo `0600`, uid 10001.
- **Docker:** usuario no root, raíz de solo lectura, `cap_drop ALL`, `no-new-privileges`, puerto en loopback, sin credenciales en la imagen (las variables con `PASS/SECRET/KEY` son nombres de configuración y `GPG_KEY` es el identificador público de la imagen base de Python).
- **Variables de entorno:** `RELAY_ALLOW_INSECURE` y `ADMIN_PASSWORD_FILE` no se reenvían al contenedor; el arranque falla sin contraseña inicial.

## 5. Estado del README y la documentación

- **README:** URL real (`git clone https://github.com/pd-LuisOlivares/nostr-nip46-remote-signer.git`), inicio rápido de 13 pasos, requisitos para un evaluador sin archivos del desarrollador, aclaración de los puertos 8000/8001, resultado del clon limpio y correcciones del modo continuo. Explica instalar (§5), ejecutar (Inicio rápido y §8, §10), probar (§9), configurar (§7) y limitaciones (§13). Una prueba automatizada comprueba que el comando y las credenciales del inicio rápido coinciden con `deploy/demo.env`.
- **`docs/decisions.md` y `docs/phase-1.0B-B6.2-plan.md`:** PASS real documentado como **declaración del propietario**, con una tabla de lo confirmado frente a lo no respaldado por evidencia.
- **Pendiente en el README:** no hay una guía de resolución de problemas de Docker en Windows (WSL, Docker Desktop detenido, puerto ocupado) más allá de «Si algo no funciona» del inicio rápido y de `APP_PORT`.

## 6. Arquitectura real de los puertos 8000 y 8001 (Fase 4) y propuesta

**Hechos verificados** (`docker ps -a`, `docker inspect`, `compose.yaml`, `app/main.py`):

| Elemento | Hecho |
|---|---|
| **8001** | Contenedor `nostr-nip46-remote-signer-app-1` (proyecto `nostr-nip46-remote-signer`, imagen `d17-continuous`), el entorno B6.2/validación real. Sirve **toda la aplicación**: API `/api/*`, `/health` y la interfaz estática en `/` (`StaticFiles` en `app/main.py`) |
| **8000** | **Nada escucha ahora.** Es el valor por defecto de `compose.yaml` y del perfil demo (proyecto `nip46-evaluacion`, imagen `:evaluation`, volumen `nip46-evaluacion_app_data`), **aún no creados en esta máquina**. Misma aplicación y mismo código, otra base |
| **Interfaz del firmante** | `app/static/` (HTML/CSS/JS), servida por el mismo proceso FastAPI que la API. No hay otra interfaz del producto |
| **Cliente NIP-46 de laboratorio** | `lab/manual/client_web/` (Node, NDK 2.12.2 real, puerto **18080**) dentro de `lab/manual/compose.manual.yaml` (proyecto `nip46-manual`, con su relay local 17777 y su propio `app` con imagen `manual-b61d`). Los contenedores existen y están detenidos. **No forma parte de `compose.yaml`** (el único servicio del producto es `app`) |
| **Bases SQLite** | Una por proyecto Docker: `/data/nip46.db` en el volumen `<proyecto>_app_data`. Hoy: `nostr-nip46-remote-signer_app_data` (B6.2) y `nip46-manual_app_data` (laboratorio). **No se comparten.** La del perfil demo se creará al primer arranque |
| **Administradores** | `AdminAccounts.prepare()` crea el administrador solo si la tabla está vacía y hay `ADMIN_PASSWORD`; después la variable se ignora. El de B6.2 se **importó** de `data/b62.db` con `deploy/import_admin_db.py` y su contraseña se restableció el 2026-11-22 |
| **Conflicto detectado** | El README documenta el cliente de laboratorio con el firmante en `127.0.0.1:8000` **y** el perfil demo también usa `8000`: **no pueden ejecutarse a la vez** (mismo puerto del host, proyectos distintos). Además, las instancias 8000 y 8001 **no son un mismo despliegue**: son dos proyectos independientes con bases distintas |

**Propuesta concreta (no implementada):**
1. **Un único camino para el evaluador:** `deploy/demo.env` en el puerto 8000, tal como está. Es lo más simple (un comando, credenciales en el README, sin pasos manuales).
2. **Declarar `continuous.env`/`b62.env` como perfiles del propietario** («validación real»), fuera del camino del evaluador: moverlos a `deploy/validation/` o marcarlos así en el README (cambio documental menor).
3. **Eliminar el choque del 8000:** pasar el firmante de la demostración de laboratorio a otro puerto (p. ej. 18000) en `lab/manual/compose.manual.yaml` y en el README.
4. **Una vez capturada la evidencia**, detener el contenedor de 8001 y documentar que no forma parte del entregable; así quedan una sola instancia activa y un solo puerto documentado.
5. Mantener bases separadas por proyecto (aislamiento) y **no** introducir una base compartida.
Requiere decisión del propietario (cambia puertos y organización de `deploy/`).

## 7. Riesgos y bloqueos
- **Bloqueo para publicar la evidencia del PASS:** sin auditoría capturada (se pierde al reiniciar el contenedor de B6.2).
- **Riesgo reputacional/privacidad:** correo de autoría público (M-1) y transcripciones de IA (B-8).
- **Riesgo operativo:** firmante B6.2 posiblemente activo con la identidad B4 (M-2).
- **Cadena de suministro:** base mutable y sin hashes (B-2).
- **Sin bloqueos técnicos** para continuar con las demás tareas seguras. No se detectó ningún problema que exija modificar código funcional.

## 8. Pendientes P-47, P-48 y P-49 (sin aprobación expresa; **no implementadas**)
| # | Qué es | Recomendación (sin implementar) |
|---|---|---|
| P-47 | Volver a emparejar con la **misma clave de cliente** tras revocar o caducar (hoy hay que usar una clave nueva) | Baja prioridad: no se sabe si Stacker News reutiliza su clave de cliente (supuesto sin verificar). Decidir después de observarlo |
| P-48 | Límite propio (p. ej. 10/min) para remitentes **no autorizados**; hoy un desconocido puede agotar el límite global de 120/min y retrasar a clientes legítimos | Prioridad media si el relay es público; cambio pequeño y localizado. Requiere aprobación |
| P-49 | Mostrar «Reconectando, intento n de 5» y el motivo de agotamiento | Baja; parcial (estado «Reconectando» ya existe) |

## 9. Próximas acciones recomendadas
1. Detener el firmante de B6.2, cambiar la contraseña de `b62-admin` y, si se quiere evidencia, repetir la prueba real con captura sanitizada de la auditoría (autorización nueva).
2. Revisar este informe y los commits locales; decidir M-1 y B-8 antes de publicar más.
3. Decidir la propuesta de §6 (puertos y organización de `deploy/`).
4. Decidir P-47, P-48 y P-49.
5. Valorar el digest de la imagen base y los hashes de dependencias (B-2).
6. Autorizar el push de los commits locales de esta jornada (**no se hizo push**).

## 10. Archivos modificados en esta jornada
`README.md`, `docs/decisions.md`, `docs/phase-1.0B-B6.2-plan.md`, `docs/HANDOFF.md`, `docs/NIGHTLY-REVIEW.md` (nuevo), `docs/ai-log.md` (entrada 52), `tools/ai_sessions_manifest.json` (interacción 52) y las transcripciones `docs/ai-sessions/…50…`, `…51…` y `…52…` (la 52 es nueva). **Ningún archivo de `app/`, `deploy/`, `compose.yaml`, `Dockerfile` ni `tests/`.** Recursos temporales (clon, proyecto Docker `nip46-clonetest` e imágenes propias) eliminados.

## 11. Trazabilidad (Fase 5) y verificaciones finales

- **`docs/ai-log.md`:** entradas 50 (PASS real confirmado por el propietario, restablecimiento de contraseña y cierre de jornada), 51 (consolidación y push de `70b4481`) y 52 (esta jornada); manifiesto con las interacciones 50 a 52.
- **Transcripciones 50, 51 y 52: PARCIAL.** La sesión de origen (`97ea8763…`) sigue abierta, así que los archivos crecen y **deben reexportarse al cerrarla**; su cabecera indica hasta qué instante llegan. No son reconstrucciones. La contraseña administrativa de B6.2 se **redactó** al exportar y no aparece en ningún archivo del repositorio (comprobado con búsqueda literal y del fragmento final).
- **`python tools/ai_sessions.py check`:** ejecutado justo tras la exportación final (resultado en el informe de entrega). Como la sesión sigue abierta, vuelve a marcar desfase en cuanto se añade un mensaje nuevo; es el comportamiento esperado de una interacción parcial.
- **Pruebas del árbol principal tras los cambios de documentación:** `python -m pytest` → **1037 passed, 27 skipped, 0 failed** (26 de Docker sin `E2E_DOCKER`, 1 de permisos POSIX); `tests/test_ai_traceability.py` y `tests/test_deploy_profile.py`: 78 passed; `git diff --check` limpio.
- **Escaneo de secretos de los archivos modificados o nuevos:** sin contraseñas reales, claves privadas, JWT, cookies ni URI `bunker://`; los 3 avisos del escáner son marcadores `Read-Host` del README y el único hexadecimal de 64 caracteres es la clave **pública** de B4.
- **Commit:** local, sin push (ver el informe de entrega).
