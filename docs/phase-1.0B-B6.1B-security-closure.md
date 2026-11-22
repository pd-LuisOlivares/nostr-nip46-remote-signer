# B6.1B: cierre de seguridad antes de la validación real (P-38 corregido; P-41 verificado)

**Fecha:** 2026-11-21 · **Base:** `4b9e51eba698c3434f4fee3b0f6a5224e60e504b` más los cambios locales sin commit de B6 etapa 1 y B6.1A (conservados) · **Veredicto: PASS con observaciones** · Sin commit ni push.

> **Actualización B6.1C (2026-11-21):** el hallazgo abierto de **P-41** (OOM con ráfagas de 5 verificaciones) y **P-42** se cerraron en [`phase-1.0B-B6.1C-p41-p42.md`](phase-1.0B-B6.1C-p41-p42.md) con la alternativa A (una verificación activa por proceso). La prueba `xfail` de memoria se eliminó. Las cifras de este informe son anteriores.

Validación **local**: no hubo conexión a Stacker News ni a relays públicos, no se usó la identidad de B4 y no se generó ninguna firma real (todas las firmas de las pruebas son con claves efímeras de prueba). `AGENTS.md` y `CLAUDE.md` no se modificaron. No se implementó P-39 ni se rediseñó P-40.

## 1. Causa raíz de P-38

En `SignerService._on_sign` la política (11 comprobaciones, incluida la antigüedad de `created_at` frente a `SIGNER_WINDOW_S`) se evaluaba **una sola vez, antes** de ofrecer la solicitud al operador. La aprobación puede llegar hasta `APPROVAL_TTL_S` (5 a 600 s) después. Al aprobarse, `_sign_once` firmaba el **resultado de la evaluación antigua** y solo comprobaba repetición del reto y tope de firmas. Consecuencias: (a) una plantilla ya más vieja que la ventana se firmaba igual; (b) nada comprobaba que la aprobación siguiera vigente, que el firmante o el cliente siguieran activos, ni que lo que se firmaba fuera exactamente lo aprobado. La aprobación humana era necesaria pero se trataba como suficiente.

## 2. Corrección exacta

Punto de firma: `SignerService._on_sign` → tras `await self._ask(...)` (la decisión humana) se llama a un método **nuevo y síncrono**, `_revalidate_and_sign` (`app/services/signer.py`), que sustituye a la llamada directa a `_sign_once`. Al ser síncrono (**sin ningún `await`** entre las comprobaciones, el consumo de la aprobación y el uso de la clave), ninguna otra tarea puede intercalarse: se evitan las condiciones de carrera entre aprobación, revalidación y firma.

Orden de las comprobaciones, con el reloj de **ahora**:
1. **Aprobación** (`ApprovalRegistry.consume`, nuevo): la gasta en ese instante y rechaza si ya estaba consumida (`aprobacion_consumida`), si no es una decisión humana aprobada (`aprobacion_no_vigente`) o si venció (`aprobacion_caducada`, mismo criterio `>=` que `resolve`). **Queda consumida aunque se rechace** (falla de forma segura: no se reintenta con la misma decisión).
2. **Firmante activo**: estado `READY`, sin parada solicitada ni motivo de cierre (cubre la vida máxima de sesión y la parada del operador) (`firmante_no_activo`).
3. **Cliente activo**: la conexión del cliente no venció ni fue revocada (`cliente_no_activo`).
4. **Política completa de nuevo** (`evaluate` con la hora actual): vigencia temporal del evento y ventana, origen, método, contenido, estructura, tipo, identidad/id, **repetición** y el resto de las 11 comprobaciones (`politica_incumplida`, con los nombres de las comprobaciones que fallaron).
5. **Misma solicitud**: la huella SHA-256 de lo que se va a firmar (`template_binding`: identidad, `kind`, `created_at`, etiquetas y contenido) debe coincidir con la que se calculó al **ofrecer** la solicitud al operador y se guardó en `PendingRequest.binding` (`solicitud_alterada`).

Si algo falla: respuesta genérica `unauthorized` (sin detalle hacia el cliente), **ninguna firma ni evento firmado publicado**, el reto **no** se gasta (el cliente puede reintentar, pero cada reintento crea una solicitud nueva que exige otra aprobación humana: no hay aprobaciones implícitas ni firmas automáticas) y queda registro. Si todo pasa se firma la plantilla **re-evaluada ahora** (idéntica a la aprobada por el vínculo) y se conservan la autoverificación, el tope de firmas y el consumo atómico del reto de `_sign_once`.

**Registro seguro:** nuevo evento de auditoría `revalidation` en la lista blanca (`request_id`, `ok`, `reason`, `failed`, `created_at_age_s`; nunca la plantilla, el reto, la huella ni claves) y el `decision` existente con `reason=revalidacion_<motivo>`.

**No se modificó:** ningún límite de seguridad (`SIGNER_WINDOW_S`, `APPROVAL_TTL_S`, topes), la política, la criptografía, NIP-46, JWT ni la autorización humana. La revalidación solo puede **denegar más**, nunca autorizar más.

Archivos: `app/services/signer.py`, `app/services/approvals.py` (`binding`, `consumed`, `consume`), `app/services/policy.py` (`template_binding`), `app/services/audit.py` (evento `revalidation`).

## 3. Pruebas nuevas (relojes controlados y dobles locales; sin servicios externos)

La prueba `xfail` estricta de P-38 se convirtió en una **regresión normal** (`test_approval_given_after_the_policy_window_elapsed_must_not_sign`, comprueba además `failed == ["created_at"]` y edad 300 s). En `tests/services/test_signer.py`:

| Escenario pedido | Prueba |
|---|---|
| Válido al solicitar y al firmar; flujo manual intacto | `test_valid_when_requested_and_still_valid_when_signing_keeps_the_manual_flow` (sin aprobación no hay firma; con 30 s de espera firma; auditoría `ok`) |
| Válido al principio, vencido antes de firmar | `test_approval_given_after_the_policy_window_elapsed_must_not_sign` y `test_the_event_is_valid_up_to_the_exact_window_and_not_one_second_later` (120 s firma, 121 s no) |
| Ventana del firmante vencida | `test_expired_session_window_of_the_signer_prevents_signing` y `test_a_connection_that_expired_while_waiting_for_approval_cannot_get_a_signature` |
| Aprobación caducada | `test_an_approval_that_expired_before_signing_is_refused` |
| Aprobación ya consumida | `test_an_approval_that_was_already_consumed_cannot_be_used_again` |
| Solicitud alterada tras aprobarse | `test_a_request_altered_after_approval_is_refused` |
| Rechazo sin firma ni publicación | `assert_refused_without_signature` en todas las anteriores (sin `sign_ok`, `signatures == 0`, ningún evento de la identidad publicado, sin solicitudes pendientes nuevas) |
| Nada implícito tras un rechazo | `test_a_rejected_revalidation_signs_nothing_and_a_new_request_needs_a_new_human_approval` |
| Rechazada por el operador: nunca llega a la revalidación | `test_a_denied_request_never_reaches_the_revalidation_or_the_key` |
| Registro sin secretos | `test_revalidation_audit_never_contains_secrets_or_the_template` |
| Se firma exactamente lo aprobado | `test_the_signature_is_made_over_exactly_the_approved_template_after_revalidation` |

Más pruebas unitarias de `ApprovalRegistry.consume` (consumo único, no vigente, límite exacto de caducidad) y de `template_binding` (determinista y sensible a cada campo). **Comprobación de mutación** (cada comprobación se anuló por separado y se restauró el código desde copia, verificado byte a byte): A (política con la hora de la solicitud, el comportamiento antiguo) detectada por 4 pruebas; B (sin consumo/vigencia de la aprobación) por 3; C (firmante activo) por 1; D (cliente activo) por 1; E (vínculo solicitud-firma) por 1. La mutación F (quitar solo `not fresh.ok`) no se detecta porque es **equivalente**: una política fallida ya deja `template = None`, que bloquea igualmente (defensa redundante).

## 4. P-41: Argon2id con memoria limitada (resultado)

Método: el contenedor **real del producto** (`nostr-nip46-remote-signer:dev`, Python 3.12.16, raíz de solo lectura, sin capacidades) con `--memory X --memory-swap X` (sin swap), Docker Desktop (cgroup v2). Se mide el arranque (que calcula un Argon2id de 64 MiB para crear el administrador), un login correcto y ráfagas de verificaciones **simultáneas** (el limitador admite hasta **5 en vuelo**, el peor caso: 5 × 64 MiB). Memoria en reposo del contenedor: **43 MiB**.

| Límite | Arranque + login correcto | Ráfaga simultánea | Resultado |
|---|---|---|---|
| 1 GiB, 512 MiB, 384 MiB | OK | 5 y 8 (200/401/429 sin cortes) | **OK** |
| 352 MiB, 320 MiB | OK | 5 | **OOM-kill** (`exit 137`, `OOMKilled=true`) |
| 256 MiB | OK | 1, 2 y 3 → 401; **5 → OOM-kill** | OK hasta 3 simultáneas; **falla con 5** |
| 192, 160 y 128 MiB | OK (arranque y login) | solo se probó 5 | un login a la vez funciona; la ráfaga de 5 falla |

Conclusión: el perfil actual **funciona para el uso previsto** (un operador, un inicio de sesión a la vez) **desde 128 MiB**, y para la ráfaga máxima del limitador **desde 384 MiB** (umbral entre 353 y 384 MiB, medido). **Con 256 a 352 MiB una ráfaga de 5 intentos simultáneos mata el contenedor** (un tercero local podría provocarlo; el reinicio automático de Compose lo recupera, pero se pierden las sesiones y el firmante en curso). Sin límite de memoria (la configuración por defecto de `compose.yaml`) no ocurre. Pruebas: `tests/e2e/test_docker_argon2_memory.py` (con `E2E_DOCKER=1`): los casos que funcionan pasan como aserciones normales (128 MiB × 1, 256 MiB × 3, 384 MiB × 5, 512 MiB × 8) y el fallo se documenta con un `xfail` estricto (256 MiB × 5).

**P-41 queda verificado y con un hallazgo abierto.** No se cambiaron los parámetros de Argon2id (no hay evidencia que lo justifique para el uso previsto). Alternativas, **no implementadas** (decisión suya):
- **A (recomendada):** limitar a 1 o 2 las verificaciones Argon2id concurrentes (un semáforo en el login). Pico ≈ 43 + 64 × N MiB (≈ 107 MiB con N = 1: cabe en 128 MiB); el costo es latencia solo bajo ráfaga (5 × ~70 ms). No cambia los parámetros ni el nivel de seguridad.
- **B:** documentar el mínimo (384 MiB) y fijar `mem_limit` en `compose.yaml` (p. ej. 512 MiB) para no depender del anfitrión. Solo configuración.
- **C:** bajar el costo de memoria de Argon2id (p. ej. ~19 MiB, t = 2, p = 1). Reduce el margen frente al perfil RFC 9106; solo con una razón concreta.

## 5. Regresión completa

| Comprobación | Resultado |
|---|---|
| `pytest -q -rs -rx` con `E2E_DOCKER=1` (equipo de desarrollo, con los vectores NIP-44) | **783 passed, 1 skipped, 1 xfailed** (123 s). Omitida: permisos POSIX (Windows). `xfailed`: P-41 |
| `pytest -q -rs` sin `E2E_DOCKER` | 776 passed, 9 skipped (68 s): 5 de memoria Argon2 + 1 NDK + 2 persistencia (Docker) y 1 POSIX |
| Copia limpia (exportación del árbol de trabajo, venv nuevo, instalación según el README, `pytest -q -rs`) | pip sin errores, `pip check` limpio; **768 passed, 17 skipped** (71.71 s) |
| E2E de navegador (Chrome) | 19 aprobadas (incluidas en lo anterior): login, cookies, CSRF, revocación y logout siguen funcionando |
| E2E Docker (SQLite persistente tras `restart`/`down`/recreación, NDK 2.12.2 real con el login nuevo) | aprobados (incluidos en lo anterior) |
| Regresión NIP-46 `lab/run_product_regression.py` y `--api` (NDK 2.12.2 real, red interna) | **E1, E2, E3 y E8: PASS en ambos modos** |
| `mypy --strict app` | `Success: no issues found in 35 source files` |
| `pip check` / `git diff --check` | limpios |
| Cobertura de líneas y ramas de `app/` | 99 % total; el código nuevo de la revalidación (`_revalidate_and_sign`, `consume`, `template_binding`) está al 100 % |

## 6. Efectos en el comportamiento y riesgos pendientes

- **Efecto deliberado:** una aprobación que llega cuando la plantilla ya tiene más antigüedad que `SIGNER_WINDOW_S` (por defecto 120 s) **ya no firma**. La ventana efectiva de aprobación es `SIGNER_WINDOW_S − antigüedad de la plantilla al solicitar`, aunque `APPROVAL_TTL_S` sea mayor. No se alteraron los límites. B4 (aprobación en 7,8 s) no se habría visto afectado.
- **P-42 (nuevo, opcional):** la interfaz muestra «caduca en N s» según `APPROVAL_TTL_S` y, si la revalidación rechaza tras una aprobación humana, la solicitud figura como «aprobada» en Recientes aunque **no hubo firma** (el motivo está en la auditoría: `revalidation` y `decision`). Propuesta: mostrar el rechazo y la ventana real; no se implementó (no se amplían funcionalidades).
- **P-41:** abierto (ráfaga de 5 verificaciones con 256 a 352 MiB). Hasta decidir, no limite la memoria del contenedor por debajo de 384 MiB o no la limite.
- Siguen: P-39 (sin cambio de contraseña guiado), P-40 (límite de login global), sin *hashes* en `constraints.txt`, pruebas de navegador solo en Chrome, plataformas no probadas (Linux/macOS sin Docker, arm64), y la verificación «copia limpia» sigue siendo una exportación del árbol de trabajo (no hay commit).
- El cálculo de P-41 se hizo en un solo anfitrión (Docker Desktop); otros anfitriones pueden diferir en la memoria base.

## 7. Estado de Git

Sin commit, sin push, historial intacto. HEAD sigue en `4b9e51e` y coincide con `origin/main`; los cambios de B6 etapa 1, B6.1A y B6.1B están en el árbol de trabajo. Archivos de esta iteración: ver el informe final y `docs/ai-log.md` (interacción 35).

## 8. Reproducibilidad (copia limpia)

Exportación del árbol de trabajo (archivos rastreados y nuevos no ignorados) a una carpeta vacía, venv nuevo e instalación con `pip install -c constraints.txt -e ".[dev]"` según el README: instalación sin errores, `pip check` limpio y **768 passed, 17 skipped**. Omitidas: 8 vectores NIP-44 (archivo no versionado), 8 pruebas de Docker (`E2E_DOCKER`) y 1 de permisos POSIX (Windows). No se creó `data/` ni ninguna base. Sigue siendo una exportación y no un `git clone` literal porque no hay commit.

## 9. Preparación para B6.2

1. **Su decisión** sobre P-41 (recomiendo la alternativa A), y opcionalmente P-39, P-40 y P-42.
2. **Revisión y, con su autorización, commit y push** de B6 etapa 1, B6.1A y B6.1B (revisar secretos con `git diff --cached`).
3. **Verificación con un `git clone` real** del commit publicado (instalación con el README, suite, `docker compose build --no-cache`, `docker compose up --build -d` con `ADMIN_PASSWORD` por entrada oculta, ingreso por la interfaz).
4. **Compuerta operativa de B6 real** (requiere su autorización expresa, con alcance): repetir el inicio de sesión en Stacker News desde la interfaz con el nuevo ingreso y la misma identidad de B4 (importada por la interfaz), comprobando la persistencia de la sesión al recargar; una firma, aprobación humana, ventana ≤ 15 min, sin reintentos. Tenga presente P-38: con la revalidación, apruebe **dentro de la ventana** (`SIGNER_WINDOW_S`, 120 s por defecto, menos la antigüedad de la plantilla).
5. Cierre documental y exportación de las transcripciones pendientes (interacciones 32 a 35).

**Veredicto: PASS con observaciones.** P-38 está corregido, probado y verificado por mutación; P-41 está verificado con evidencia y con un hallazgo abierto y documentado (alternativas propuestas, sin cambiar parámetros); la regresión completa pasa.
