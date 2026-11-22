# Fase 1.0B, B6.1D — cierre documental de la validación local (2026-11-21)

**Estado: B6.1D CERRADA con PASS (validación local).** Esta validación es **local** (relay y cliente de laboratorio, sin Internet). **No** es una validación con Stacker News: la interoperabilidad real es B6.2, que sigue **pendiente** (ver [`phase-1.0B-B6.2-plan.md`](phase-1.0B-B6.2-plan.md)).

## 1. Decisión del propietario

La validación local B6.1D-R3 **se mantiene permanentemente** como parte del proyecto. No se reemplaza ni se elimina el cliente web local. Se añade, aparte, una segunda validación de interoperabilidad real (B6.2). Las dos matrices son independientes (§4 y el plan de B6.2).

## 2. Resultado de las comprobaciones manuales

| Dato | Valor | Origen |
|---|---|---|
| Pruebas automatizadas (`E2E_DOCKER=1`) | 842 passed, 1 skipped | Ejecución del agente al cierre de B6.1D-R3 (ver [`phase-1.0B-B6.1D-R3-web-client.md`](phase-1.0B-B6.1D-R3-web-client.md)) |
| Comprobaciones manuales | **7 de 7 PASS** | **Declaración del propietario**, que las ejecutó en el navegador con la pila de demostración |
| Cliente | NDK 2.12.2 real, en Node (`lab/manual/client_web/`) | Verificado por pruebas y por el registro del cliente |

El propietario **no transcribió al agente el detalle de cada comprobación**. El detalle de §3 es la **evidencia técnica corroborante** de la auditoría del firmante; no sustituye la declaración del propietario ni la reconstruye. Lo que consta del propietario es: NDK real, firma válida recibida y verificada, solicitudes inválidas rechazadas, firma fuera de ventana rechazada y ninguna firma no autorizada.

## 3. Evidencia técnica corroborante (auditoría sanitizada)

Archivo: [`docs/evidence/b6.1d-r3-manual-audit-2026-11-21.txt`](evidence/b6.1d-r3-manual-audit-2026-11-21.txt). Solo identificadores truncados, hashes parciales y contadores (verificado con `lab/tools/b4_check_evidence.py`: «Sin fugas»). 71 entradas en 2 sesiones del firmante (ventana de firma 45 s):

- `connect` aprobado por una persona (latencias de 3,0 s y 2,3 s) y `get_public_key` respondido.
- Dos `sign_event` firmados (`sign_ok` ×2, `self_verify` verdadero), cada uno precedido de `pending_created`, `decision approved=true reason=humano` y `revalidation ok`.
- Solicitudes rechazadas por la política **sin tarjeta de aprobación**: origen, `kind`, método (×2), contenido, `created_at` (antigüedad 600 s), reto + repetición y repetición.
- Dos solicitudes válidas **denegadas por la persona** (`approved=false`).
- `response_published relay_ok=true` en todas las respuestas; `session_end detenido_por_el_operador` con 1 firma en la primera sesión.
- Solicitudes finales: `connect` aprobada; `sign_event` aprobada con `outcome=signed`; `sign_event` denegada.
- Registro del cliente web: sin datos sensibles (eventos de arranque, operaciones, sesiones).

Límite: la segunda sesión seguía activa al volcar la auditoría (sin `session_end`), y la auditoría no demuestra por sí sola que la persona observó cada resultado en pantalla: eso es la declaración del propietario.

## 4. Matriz A — validación local B6.1D (independiente de B6.2)

Leyenda: **PASS automatizado** = pytest/E2E sin intervención humana; **PASS manual** = confirmado por el propietario; **FAIL**; **NO PROBADO**.

| # | Comprobación local | Automatizado | Manual (propietario) | Estado |
|---|---|---|---|---|
| A1 | Cliente NDK 2.12.2 **real** se conecta con la URI de un solo uso | PASS (E2E Docker) | PASS | **PASS** |
| A2 | `connect` y `sign_event` exigen aprobación humana; el cliente no puede aprobar ni alcanzar al firmante | PASS (E2E, aislamiento de redes) | PASS | **PASS** |
| A3 | Firma válida recibida y **verificada** por el cliente (id, BIP-340, identidad, plantilla, reto) | PASS (E2E, verificador con mutaciones 14/14) | PASS | **PASS** |
| A4 | Solicitudes inválidas rechazadas (origen, `kind`, método, contenido, reto, repetición) | PASS (política, E2E) | PASS | **PASS** |
| A5 | Firma fuera de ventana rechazada (plazo efectivo y revalidación P-38) | PASS (E2E de navegador) | PASS | **PASS** |
| A6 | Ninguna firma sin autorización (denegar no firma; tope de firmas) | PASS | PASS | **PASS** |
| A7 | Ingreso con usuario y contraseña, cookie `HttpOnly`/`SameSite=Strict`, CSRF y límites | PASS | Implícito (el propietario operó el panel); **no transcrito** | **PASS** (automatizado; manual no transcrito) |

Del propietario solo consta la declaración «7 de 7 PASS» y los resultados resumidos en §2 (A1, A3, A4, A5, A6). La correspondencia de las filas A1–A7 con sus siete puntos, y las columnas «Manual» de A2 y A7, son **del agente** y el propietario puede corregirlas. **NO PROBADO en B6.1D** (por diseño, es local): Stacker News, relays públicos, la identidad de B4 y NIP-42 `AUTH` real.

## 5. Qué se conserva (no se modifica ni se elimina)

| Elemento | Ubicación |
|---|---|
| Cliente web local (NDK real, Node) | `lab/manual/client_web/` |
| Pruebas E2E del cliente web | `tests/e2e/test_manual_client_web.py` (14, Docker) y `tests/test_manual_client_static.py` (7, estáticas) |
| Configuración Docker del laboratorio | `lab/manual/compose.manual.yaml` (con el `compose.yaml` del producto) |
| Cliente de línea de comandos y comprobación | `lab/manual/local_client.py`, `lab/manual/check_live.py` |
| Instrucciones de uso | [`phase-1.0B-B6.1D-R3-web-client.md`](phase-1.0B-B6.1D-R3-web-client.md) y `README.md` |
| Evidencia sanitizada | [`docs/evidence/b6.1d-r3-manual-audit-2026-11-21.txt`](evidence/b6.1d-r3-manual-audit-2026-11-21.txt) |

La pila de demostración (`nip46-manual`) puede seguir levantada: B6.2 usa **otro** puerto y **otro** nombre de host para no mezclar cookies (ver el plan).
