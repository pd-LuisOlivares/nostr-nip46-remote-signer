# Interacción 43: Modo continuo, Paso 1: configuración (SIGNER_MODE, REQUESTS_PER_MIN y AUTO_SIGN_PER_HOUR)

| Campo | Valor |
|---|---|
| Fecha del primer prompt (UTC) | 2026-11-22T02:35:58.839Z (America/Santiago = UTC-3) |
| Fase | 1.0B |
| Agente | Claude Code (extensión de VS Code, versión 2.1.330) |
| Modelo | claude-sonnet-5-5 (campo `model` de los registros de sesión) |
| Nivel de razonamiento | high (campo `effort` de los registros de sesión) |
| Sesión | 97ea8763-694e-4b53-8496-52b85c37bc64 |
| Origen de la transcripción | Archivo de sesión local de Claude Code (JSONL), extraído con `tools/ai_sessions.py`; no reconstruido |
| Hasta (UTC) | 2026-11-22T02:42:51.082Z |
| Estado | PARCIAL (la sesión de origen permanecía abierta al momento de la exportación) |

**Qué contiene y qué no.** Prompts del propietario (sin las etiquetas `pasted_content`, los bloques del editor ni los recordatorios del sistema) y todo el texto visible de las respuestas de Claude Code, en orden. Las llamadas a herramientas se indican con una línea de marcador; su contenido y sus salidas **no** se incluyen (los archivos resultantes están en el repositorio y los resultados de las pruebas, en `docs/decisions.md`). **No se incluye razonamiento interno del modelo** ni contexto del sistema. Las marcas `<!-- fecha -->` son del archivo de sesión.

**Redacción aplicada** (patrones y lectura de los hallazgos): URI `bunker://`, claves `nsec`, secretos de conexión, JWT, tokens `Bearer`, hashes de contraseña, contraseñas, correos, rutas locales, usuario local y nombre del autor. Las cadenas hexadecimales de 64 caracteres se clasifican por contexto: se conservan las claves **públicas**, los identificadores y las huellas SHA-256 necesarios para entender la evidencia (revisadas una a una) y la exportación se detiene ante cualquier duda. La ruta absoluta del proyecto se acortó a ruta relativa. Redacciones en este archivo: ruta-del-proyecto: 12, usuario-local: 1.

---

## Prompt del propietario (2026-11-22T02:35:58.839Z)

He revisado las aclaraciones y apruebo la arquitectura de firmante continuo con las siguientes decisiones definitivas.

### Decisiones aprobadas

1. `SIGNER_MODE=continuous` será el comportamiento predeterminado de la aplicación, de forma consistente tanto en `Settings()` como en `Settings.from_env()` y Docker Compose.

2. `deploy/b62.env` establecerá explícitamente `SIGNER_MODE=supervised`, preservando el comportamiento de validación anterior.

3. La firma automática se limitará exclusivamente a eventos de autenticación de Stacker News `kind: 27235`, manteniendo todas las comprobaciones de política, revalidación inmediata, protección anti-replay y auditoría.

4. La casilla «Permitir firmar automáticamente el login de Stacker News» estará desmarcada por defecto. El administrador deberá habilitarla expresamente durante la aprobación del emparejamiento.

5. JWT y CSRF seguirán protegiendo las operaciones administrativas. La autorización NIP-46 se gestionará por conexión, no mediante el JWT del administrador.

6. Apruebo los siguientes límites iniciales para el modo continuo:
   - `REQUESTS_PER_MIN=30` por conexión.
   - Límite global de 120 solicitudes por minuto.
   - `AUTO_SIGN_PER_HOUR=6` por conexión.
   - Intervalo mínimo de cinco segundos entre firmas.
   - `CONNECTION_TTL_S=28800` (ocho horas).
   - `SECRET_TTL_S=300`.
   - `APPROVAL_TTL_S=300`.

7. Apruebo la reconexión automática acotada al relay con esperas de 2, 5, 10, 20 y 40 segundos, conservando las conexiones autorizadas durante las desconexiones recuperables.

8. La creación de una identidad temporal será el camino principal del README, con importación de una identidad existente como alternativa.

9. No persistiremos claves privadas ni conexiones entre reinicios. Esta limitación debe quedar documentada.

10. No ejecutaremos todavía la validación real de Stacker News. La realizaremos sobre la versión final en Docker.

### Autorización de implementación: solo Paso 1

Autorizo exclusivamente implementar la configuración y validación de las nuevas variables:

- `SIGNER_MODE`
- `REQUESTS_PER_MIN`
- `AUTO_SIGN_PER_HOUR`

Incluye los cambios mínimos necesarios en `app/config.py`, `compose.yaml`, `.env.example`, `deploy/b62.env` y las pruebas unitarias correspondientes.

Asegura que los valores predeterminados sean consistentes y que el modo `supervised` conserve su comportamiento anterior.

### Restricciones

- No implementes todavía cambios en `SignerRuntime`, conexiones, firmas, reconexión ni interfaz.
- No modifiques SQLite ni la instancia Docker B6.2 actualmente en ejecución.
- No detengas ni reinicies contenedores.
- No reconstruyas imágenes ni descargues dependencias.
- No contactes Stacker News ni el relay público.
- No hagas commit ni push.
- No establezcas T0.
- No modifiques `AGENTS.md` ni `CLAUDE.md`.

Ejecuta las pruebas unitarias pertinentes y entrega los resultados, los archivos modificados y cualquier incompatibilidad detectada.

**Detente al finalizar el Paso 1 y espera mi aprobación antes de continuar.**

<!-- 2026-11-22T02:36:07.569Z -->
Empiezo leyendo cómo usan `Settings` las pruebas y el código, para medir el impacto de cambiar el valor predeterminado.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T02:36:34.655Z -->
Aplico los cambios de configuración. `Settings()` y `from_env` quedan consistentes en modo continuo, y el modo supervisado conserva los valores de antes.

> *[Llamada a herramienta: Edit — app\config.py]*

> *[Llamada a herramienta: Edit — app\config.py]*

> *[Llamada a herramienta: Edit — app\config.py]*

> *[Llamada a herramienta: Edit — app\config.py]*

> *[Llamada a herramienta: Read]*

<!-- 2026-11-22T02:36:50.416Z -->
Los comentarios del archivo eran distintos de los que recordaba. Aplico la edición con el texto exacto.

> *[Llamada a herramienta: Edit — app\config.py]*

> *[Llamada a herramienta: Edit — compose.yaml]*

> *[Llamada a herramienta: Edit — deploy\b62.env]*

> *[Llamada a herramienta: Edit — .env.example]*

<!-- 2026-11-22T02:37:05.877Z -->
Primero ejecuto la suite sin E2E para ver exactamente qué cambia con el nuevo valor predeterminado.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Edit — tests\test_config.py]*

> *[Llamada a herramienta: Write — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\97ea8763-694e-4b53-8496-52b85c37bc64\scratchpad\config_tests_block.py]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Edit — tests\test_deploy_profile.py]*

> *[Llamada a herramienta: Edit — tests\test_deploy_profile.py]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T02:39:05.422Z -->
Una de mis pruebas nuevas falla por un defecto de la propia prueba: «continuo» es subcadena del mensaje fijo «continuous», no un eco del valor. Pasa a comparar el mensaje exacto.

> *[Llamada a herramienta: Edit — tests\test_config.py]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T02:39:58.566Z -->
Todo pasa. Ejecuto también las E2E de navegador, porque usan los valores por defecto de la configuración, y compruebo que la instancia Docker siga intacta.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T02:42:51.082Z -->
**Paso 1 completado.** Las tres variables nuevas (`SIGNER_MODE`, `REQUESTS_PER_MIN`, `AUTO_SIGN_PER_HOUR`) se leen y validan, y el modo continuo es el valor predeterminado en `Settings()`, en `Settings.from_env()` y en Docker Compose. No toqué `SignerRuntime`, conexiones, firmas, reconexión ni interfaz. Tampoco toqué SQLite, `AGENTS.md` ni `CLAUDE.md`. La instancia Docker B6.2 sigue en marcha (`manual-b61d`, healthy, `/health` 200). No hice commit ni push, no establecí T0 y no hubo conexiones externas ni reconstrucciones.

## Archivos modificados
- [app/config.py](app/config.py): `SIGNER_MODES`, `DEFAULT_SIGNER_MODE="continuous"`, una tabla `MODE_DEFAULTS` y tres campos nuevos en `Settings`.
  - **Continuo:** `secret_ttl_s=300`, `connection_ttl_s=28800`, `approval_ttl_s=300`, `requests_per_min=30` (rango 1–120) y `auto_sign_per_hour=6` (rango 1–60).
  - **Supervisado:** conserva exactamente los valores de antes, 600, 1800 y 120.
  - Cualquier variable explícita reemplaza el valor por defecto del modo. Un `SIGNER_MODE` inválido da un mensaje fijo que nunca repite el valor recibido.
- [compose.yaml](compose.yaml): reenvía las tres variables con `${VAR:-}`. Vacío significa continuo.
- [.env.example](.env.example): documenta las tres variables y los plazos por modo, todo comentado.
- [deploy/b62.env](deploy/b62.env): añade `SIGNER_MODE=supervised`, con una nota.
- [tests/test_config.py](tests/test_config.py): pruebas nuevas.
- [tests/test_deploy_profile.py](tests/test_deploy_profile.py): el perfil incluye el modo y el reenvío de las tres variables.
- [tests/support.py](tests/support.py): el arnés del firmante fija el modo supervisado de forma explícita (ver incompatibilidades).

## Pruebas
| Comando | Resultado |
|---|---|
| `pytest -q -m "not e2e"` | **823 passed, 1 skipped**, 50 deselected |
| `pytest -q -m e2e` (navegador y locales, sin Docker) | **25 passed, 25 skipped** (las omitidas son las de Docker) |
| `pytest -q tests/test_config.py tests/test_deploy_profile.py` | 75 passed |
| `E2E_DOCKER=1 pytest -q tests/e2e/test_docker_b62_profile.py` (imagen local, sin build ni pull) | 1 passed |
| `git diff --check` | exit 0 |

Los archivos tocados no tienen CRLF ni espacios finales. `mypy` sigue sin estar instalado y no lo ejecuté.

Las pruebas nuevas cubren:
- que `Settings()` y `from_env({})` son iguales;
- que el modo supervisado conserva los literales anteriores;
- que una variable explícita prevalece sobre el modo;
- los rangos de los dos límites;
- que `.env.example` documenta todas las variables que lee la configuración.

## Incompatibilidades y avisos
1. **Paso 1: el modo se valida, pero el runtime aún no lo aplica.** Con el valor predeterminado continuo, el firmante todavía actúa como el supervisado, es decir, con `SESSION_TTL_S`, `MAX_REQUESTS` y `MAX_SIGNATURES`. Solo cambian los tres plazos por defecto (`secret_ttl_s`, `connection_ttl_s` y `approval_ttl_s`). Esto queda anotado en `app/config.py` y en `.env.example`. No conviene usar el producto en este estado intermedio hasta completar los pasos siguientes.
2. **Un test existente dependía de los valores por defecto.** `test_connect_expires_after_the_connection_ttl` suponía 1800 s y fallaba con 28800. No lo cambié a la fuerza: el arnés `make_rig` fija ahora `signer_mode=supervised`, `secret_ttl_s=600` y `connection_ttl_s=1800`. Esos tests siguen verificando el comportamiento supervisado real del runtime actual. Los pasos 2 a 5 añadirán el arnés del modo continuo.
3. **Mi propia prueba tenía un defecto**: «continuo» es subcadena del mensaje fijo «continuous». La corregí comparando el mensaje exacto.
4. **Instancia Docker en marcha:** `compose.yaml` y `deploy/b62.env` cambiaron, así que un futuro `docker compose up` sobre ella la **recrearía**. No lo ejecuté. La imagen `manual-b61d` ignora `SIGNER_MODE`, porque su `config.py` no la conoce. No debe ejecutarse `up` hasta tener la imagen final.
5. **Pendiente por diseño:**
   - El README (§7 y §10) sigue describiendo los valores anteriores.
   - La decisión D-17 y la entrada del registro `ai-log` se escriben en el paso 6.
   - Las constantes de 120 solicitudes por minuto globales y 5 s entre firmas se añaden en el paso 3, para no dejar código sin uso.
6. Los archivos nuevos de `deploy/` y `tests/test_deploy_profile.py` siguen sin rastrear en Git, como antes.

Me detengo aquí. Espero tu aprobación para el Paso 2 (estado en el runtime y ciclo de vida continuo).
