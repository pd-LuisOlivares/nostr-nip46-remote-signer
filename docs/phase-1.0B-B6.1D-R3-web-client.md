# B6.1D-R3: cliente web local NIP-46 y contador del plazo efectivo de firma

**Fecha:** 2026-11-21 · **Base:** `4b9e51eba698c3434f4fee3b0f6a5224e60e504b` más los cambios locales sin commit de B6 etapa 1, B6.1A, B6.1B, B6.1C y B6.1D (conservados) · **Estado:** implementado y verificado; **listo para la validación manual del propietario** (no declarada: la hará usted) · Sin commit ni push · Sin conexión a Stacker News ni a relays públicos · Sin la identidad de B4.

Qué se pidió y se hizo, según las decisiones aprobadas: (1) cliente **NDK 2.12.2 real** en Node sobre la imagen de laboratorio existente; (2) el firmante muestra el **plazo efectivo restante para firmar**, distinto del TTL de aprobación; (3) ventana de firma **45 s** y TTL de aprobación **120 s** solo en la demostración local; (4) `lab/manual/local_client.py` se **conserva** como herramienta técnica; (5) limpieza de los contenedores de las pruebas **sin borrar volúmenes preexistentes**.

## 1. Arquitectura mínima

```
Pestaña A  http://127.0.0.1:8000    firmante del producto (aprobación humana, SOLO aquí)
Pestaña B  http://127.0.0.1:18080   cliente web de laboratorio  ── NDK 2.12.2 real (NDKNip46Signer + NDKNostrRpc), en Node
                                         │  ws://relay:7777   (red client_net)
Relay local (imagen de laboratorio)  ────┤  127.0.0.1:17777 en el anfitrión
                                         │  ws://relay:7777   (red signer_net)
                                      firmante (app)
```

- **Cliente web** (`lab/manual/client_web/`): `server.mjs` (servicio `node:http`, sin dependencias nuevas), `verify.mjs` (verificación criptográfica pura), `verify.test.mjs`, `index.html`, `app.js`, `app.css`. Se monta de solo lectura en la imagen **existente** `nip46-lab-node:1.0a`; no hay imagen nueva.
- **Compose** (`lab/manual/compose.manual.yaml`, se usa **sobre** `compose.yaml`): relay del laboratorio, servicio `client-web` y **dos redes separadas** (`signer_net`: firmante + relay; `client_net`: cliente + relay). El cliente alcanza el relay pero **no** el firmante ni su API; el firmante no alcanza al cliente. Parámetros de la demostración: `SIGNER_WINDOW_S=45`, `APPROVAL_TTL_S=120` (variables `MANUAL_*` para las pruebas).
- **Qué hace la página:** pegar la URI (campo oculto); crear la sesión del cliente; `connect`, `get_public_key`, `ping`, firma válida y firma inválida (7 variantes: origen, `kind`, método, contenido, edad, reto, reutilización de reto). Por operación muestra su estado en vivo: **Pendiente de aprobación**, **Completada**, **Firmada y verificada**, **Rechazada**, **Expirada** o **Respuesta inválida**, con el id de la solicitud NIP-46, el reto (sha16) y, en una firma, las 7 comprobaciones.
- **Cómo usa NDK:** `connect` por el camino de Stacker News (`blockUntilReady`: `connect` con el secreto y después `get_public_key`); `get_public_key`, `ping` y `sign_event` por `rpc.sendRequest` de NDK (la misma capa de protocolo y cifrado, NIP-04/NIP-44). Se usa `sendRequest` directo en las firmas para recibir el **evento firmado completo** y verificarlo entero (el atajo `event.sign()` de NDK solo devuelve la firma).
- **«Firmada» solo tras verificar** (`verify.mjs`): JSON válido, campos y formatos, **id = SHA-256 del evento**, **firma BIP-340**, **clave = la identidad declarada en `get_public_key`**, **contenido idéntico a lo solicitado** y **reto idéntico**. Si falla cualquiera: «Respuesta inválida». Una respuesta que llega después de expirar nunca cuenta como éxito.

### Cambio en el firmante (mínimo, solo lectura)
`PendingRequest.sign_deadline` (= `created_at + SIGNER_WINDOW_S + 1`, el instante exacto desde el que la política deja de aceptar la plantilla) y el campo `sign_expires_in_s` en `/api/requests` (solo en firmas pendientes; `connect` no lo tiene). **No cambia** la política, la revalidación, los límites ni la autorización. La tarjeta muestra **«Plazo efectivo para firmar: N s»** (el menor entre la ventana de la política y la aprobación), la ventana, la caducidad de la aprobación y, si manda la ventana, lo dice; al llegar a cero muestra **«Ya no puede firmarse»**, avisa de que «aunque la apruebe, el firmante NO firmará» y rotula el botón **«Aprobar (ya no firmará)»**. El botón **no se desactiva a propósito**: el servidor es la autoridad y aprobar fuera de plazo debe poder verse como «Rechazada al firmar» (P-38/P-42); desactivarlo ocultaría esa revalidación y, por redondeo de reloj, podría bloquear algo que el servidor aún acepta.

## 2. Medidas de seguridad
| Requisito | Cómo se cumple y se prueba |
|---|---|
| La pestaña B nunca aprueba | El servicio no tiene credenciales ni rutas del firmante: solo `/api/session`, `/api/state`, `/api/op` (prueba estática y de red: `/api/approve`, `/api/requests/…`, `/api/signer/…` → 404). No comparte cookies ni sesión con A; el cliente **no alcanza** al firmante (redes separadas: probado con una conexión TCP real) |
| Solo relays locales | Antes de abrir nada se rechaza todo relay que no sea `ws://` a `relay`/`localhost`/`127.0.0.1`/`[::1]` (8 variantes probadas: `wss`, hosts públicos, IP privada, `127.0.0.1.evil.com`, credenciales, consulta…). 0 conexiones TCP hacia direcciones públicas en los 3 contenedores |
| Solo loopback / Host / Origin / CSRF | Publica solo en `127.0.0.1`; valida `Host` (anti DNS rebinding) y `Origin`; exige la cabecera propia `X-Lab-Client` y un token de sesión (cabecera, aleatorio, comparación en tiempo constante); **sin CORS** (el preflight no se concede) |
| CSP y cabeceras | `default-src 'none'; script-src 'self'; …; frame-ancestors 'none'`, `nosniff`, `no-store`, `X-Frame-Options: DENY`; lista cerrada de archivos estáticos (`/server.mjs`, `/verify.mjs`, `/../…` → 404); cuerpo ≤ 4 KiB; solo JSON |
| URI y claves solo en memoria | Nunca en disco, URL, registros ni respuestas (los errores no repiten la URI). Sin `localStorage`/`sessionStorage`/cookies (probado en el navegador); el campo de la URI se vacía al crear la sesión; la sesión se olvida al cerrarla, al cerrar la pestaña o a los 15 min de inactividad. Registro estructurado y **redactado** (URI, `secret=` y hex de 64) |
| Sin firmas automáticas | Sin aprobar, la operación sigue «Pendiente», el contador de firmas del firmante en 0 y la auditoría no tiene `sign_ok`; la decisión humana precede a la firma |
| Aislamiento | Sesiones de cliente con token y clave efímera propios; una no ve las operaciones de otra; token ausente o falso → 401 |
| No entra en producción | No está en `Dockerfile`, `compose.yaml` ni `.dockerignore` (prueba estática); vive en `lab/manual/` |

## 3. Pruebas y resultados
**Qué es cada cosa:** los clics de «Aprobar» de las pruebas los hace Playwright (o, en un caso, una llamada de prueba al registro de aprobaciones del firmante en proceso): son **aprobaciones automatizadas de prueba**, no las suyas. Su validación manual no está automatizada ni sustituida.

| Comprobación | Resultado |
|---|---|
| `pytest -q -rs -rx` con `E2E_DOCKER=1` | **842 passed, 1 skipped** (permisos POSIX en Windows), 0 xfailed (293 s) |
| `pytest -q -rs` sin `E2E_DOCKER` (3 ejecuciones seguidas) | 818 passed, 25 skipped, estable (107 s) |
| Copia limpia (exportación del árbol, instalación según el README) | 810 passed, 33 skipped (110 s) |
| Regresión NIP-46 con NDK 2.12.2 real (servicio y `--api`) | E1, E2, E3 y E8 en PASS en ambos |
| `mypy --strict app` · `pip check` · `git diff --check` | limpios (36 archivos) |
| Cobertura de `app/` | 99 % (`approvals.py` 99 %, `signer.py` 99 %, `schemas/control.py` 100 %) |
| Volúmenes de Docker tras la suite completa | sin cambios (57 antes, 57 después) |

**Pruebas nuevas del cliente web (`tests/e2e/test_manual_client_web.py`, 14, con `E2E_DOCKER=1`, dos navegadores reales, NDK real):** (1) verificador: 7 pruebas Node (firma alterada, id falso, otra clave, otra plantilla, basura); (2) flujo completo: `ping` previo rechazado, `connect` pendiente hasta aprobar, identidad = la del panel A, `get_public_key`, `ping`, firma válida **pendiente sin firmar** mientras nadie aprueba, 7/7 comprobaciones tras aprobar, «Firmada correctamente» en A, decisión humana antes de `sign_ok` en la auditoría; (3) las 6 variantes inválidas se rechazan **sin tarjeta** y la reutilización de un reto también; (4) aprobación fuera de plazo → «Ya no puede firmarse», «Aprobar (ya no firmará)» y «Rechazada al firmar»; (5) solicitud sin respuesta → **Expirada** en el cliente y una respuesta tardía **nunca** cuenta como éxito; (6) **dos firmas simultáneas aprobadas en orden inverso**: se firma la aprobada y la otra sigue pendiente, 7/7 para cada una (correlación por id; el reto sha16 de cada tarjeta coincide con el de su operación); (7) URI ya usada en una sesión nueva → rechazada sin llegar al operador; (8) dos sesiones de cliente aisladas; (9) reinicio del relay: el firmante termina (no reconecta en silencio), el cliente no inventa respuesta y una URI nueva sí funciona; (10) superficie HTTP cerrada (Host, Origin, sin cabecera propia, CORS, 413/415, archivos, relays y URI inválidos, rutas de aprobación inexistentes); (11) la página no guarda nada en el navegador ni muestra la URI; (12) 0 conexiones públicas y el cliente **no alcanza** al firmante; (13) ningún secreto en registros; (14) **un firmante real con la respuesta manipulada** (firma alterada, contenido alterado, respuesta de otra solicitud, firmada por otra clave) **nunca** se muestra como firma, y sin manipulación el mismo camino sí da «Firmada y verificada». Más 7 pruebas estáticas siempre activas (`tests/test_manual_client_static.py`).
**Contador (firmante):** pruebas de backend (plazo = ventana − antigüedad, no el TTL; límite exacto; `connect` sin plazo), de API y de interfaz (valores que decrecen, mayor/menor entre ventana y aprobación, «Ya no puede firmarse»).
**Mutaciones** (código restaurado y verificado después de cada una): verificador (firma, plantilla, identidad), «firma sin verificar» en el servidor, relays no locales, sin comprobación de Origin, sin cabecera propia, sin Host, sin validar el token; contador (ignora la ventana, no avisa al vencer, plazo sin el +1, plazo con el TTL, vista sin el campo). **14 de 14 detectadas.**

## 4. Limpieza Docker
Se corrigió la **única** fuga: `tests/e2e/test_docker_argon2_memory.py` borraba sus contenedores con `docker rm -f` y dejaba los volúmenes anónimos `/data`; ahora usa `docker rm -fv` (solo los volúmenes anónimos **de ese contenedor**). Las demás pruebas ya usaban `down -v` o `run --rm`. Las pruebas nuevas usan proyecto, imagen y puertos propios y `down -v` en el cierre. **No** se ejecutó `docker volume prune` ni se borró ningún volumen: los **55 volúmenes anónimos** que dejaron las ejecuciones anteriores (bases de prueba con administradores ficticios) siguen ahí; no son suyos, pero no se pueden distinguir de otros a ojo, así que se dejan para que usted decida (propuesta: un listado de solo lectura de los que contienen únicamente `nip46.db` con usuarios de prueba antes de borrar nada). El volumen `nip46-manual_app_data` (la cuenta de prueba de la demostración) y `magento246_appdata` no se tocaron.

## 5. Instrucciones de uso desde el navegador (sin PowerShell durante el recorrido)
La demostración **ya está levantada** (proyecto `nip46-manual`). Contraseña de la cuenta de prueba: ver README, «Demostración local desde el navegador».
1. **Pestaña A** `http://127.0.0.1:8000`: ingrese (usuario `admin-manual`) → «Crear identidad temporal» → «Iniciar firmante» (Listo) → «Emitir URI de un solo uso» → «Copiar».
2. **Pestaña B** `http://127.0.0.1:18080`: pegue la URI → «Crear sesión».
3. B «Conectar (connect)» → en A aparece «Conexión de un cliente» → **Aprobar** → B: *Completada*.
4. B «get_public_key» y «ping» (no requieren aprobación).
5. B «Firma válida» → en A la tarjeta muestra «Plazo efectivo para firmar: ~45 s» → **Aprobar** → B: *Firmada y verificada* (7 ✓) y A: «Firmada correctamente».
6. B «Enviar firma inválida» (cada variante) → B: *Rechazada* («Rechazo esperado»), sin tarjeta en A.
7. **Fuera de plazo:** B «Firma válida» → espere más de 45 s sin aprobar (A: «Ya no puede firmarse», botón «Aprobar (ya no firmará)») → Aprobar → B: *Rechazada*; A: «Rechazada al firmar: la política dejó de cumplirse».
8. (Opcional) Otra firma válida sin aprobar durante 150 s → B: *Expirada*.
9. Pegue la **misma** URI en una sesión nueva de B → «Conectar» → *Rechazada* (URI de un solo uso).
10. A: «Detener» y «Cerrar sesión»; B: «Cerrar sesión del cliente».

## 6. Limitaciones
- **Es un cliente de laboratorio**, no el producto ni un cliente Nostr general; no sustituye la validación real con Stacker News.
- El cliente ve «Rechazada» sin el motivo: el protocolo devuelve un `unauthorized` genérico a propósito; el motivo está en el panel A.
- «Firmada» en el firmante significa firma producida y autoverificada; en el cliente, firma **verificada criptográficamente**. La entrega por el relay se audita aparte.
- Pruebas de navegador solo en Chrome; Docker Desktop en Windows; sin soporte de varios procesos.
- Las dos redes aíslan al cliente del firmante a nivel de red de Docker, no son una barrera frente a alguien con acceso al motor de Docker.

## 7. Archivos
**Creados:** `lab/manual/client_web/{server.mjs,verify.mjs,verify.test.mjs,index.html,app.js,app.css}`, `tests/e2e/test_manual_client_web.py`, `tests/test_manual_client_static.py`, este informe.
**Modificados:** `lab/manual/compose.manual.yaml` (cliente web, redes, parámetros 45/120 s), `app/services/{approvals,signer}.py`, `app/schemas/control.py`, `app/static/app.js` (contador), pruebas (`tests/services/test_signer.py`, `test_connections_approvals_audit.py`, `tests/api/test_control_api.py`, `tests/api/test_login_capacity.py`, `tests/e2e/test_browser_login.py`, `tests/e2e/test_docker_argon2_memory.py`), `README.md`, `docs/{decisions,ai-log,handoff-2026-11-21,project-context,phase-1.0B-B6.1D-diagnosis-and-proposal}.md`. `AGENTS.md` y `CLAUDE.md` **sin cambios**; el `Dockerfile` y el `compose.yaml` del producto **no se tocaron en esta iteración** (sus cambios vienen de B6.1A: volumen de datos). `lab/manual/local_client.py` y `lab/manual/check_live.py` se conservan.
Dos correcciones de pruebas surgidas en la regresión: `test_the_deployment_runs_a_single_process` no contemplaba la frase «no use `--workers`» añadida al README en B6.1C; y la prueba real de aprobación tardía (`test_browser_login.py`) usaba una ventana de 2 s demasiado ajustada y fallaba de forma intermitente con la máquina cargada (ahora 5 s).

## 8. Estado de Git
Sin commit ni push; `HEAD` sigue en `4b9e51e` igual que `origin/main`; todo el trabajo (B6 etapa 1 a B6.1D-R3) está en el árbol de trabajo. Ver el informe final para `git status` y `git diff --check`.

## 9. Pendiente
Su validación manual con las dos pestañas (nada se da por PASS manual hasta entonces), decisión sobre los 55 volúmenes anónimos antiguos, P-39/P-40 (opcionales), y después revisión/commit/push y B6.2 con su autorización.
