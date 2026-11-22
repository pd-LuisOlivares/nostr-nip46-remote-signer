# B6.1D-R2: diagnóstico de la validación manual y propuesta de cliente de demostración en el navegador

**Fecha:** 2026-11-21 · **Estado:** diagnóstico y propuesta; **no se implementó el cliente** ni se modificó código del producto · Sin commit ni push · Sin conexión a Stacker News ni a relays públicos · Sin usar la identidad de B4.

> **Actualización B6.1D-R3 (2026-11-21):** el propietario aprobó la propuesta (NDK real en Node, contador efectivo, 45/120 s, conservar `local_client.py`, limpieza sin borrar volúmenes) y se implementó: ver [`phase-1.0B-B6.1D-R3-web-client.md`](phase-1.0B-B6.1D-R3-web-client.md).

## 1. Qué ocurrió en la prueba manual (hechos verificados)

Fuentes: auditoría sanitizada del firmante (`/api/audit`, 88 entradas, lectura), solicitudes (`/api/requests`), registro de acceso HTTP del contenedor, registro del relay local y el resumen saneado del cliente de laboratorio (`resultado_cliente.json`). Las lecturas las hizo el agente con la cuenta de prueba, sin imprimir credenciales ni claves.

**Firmas sin aprobación humana: NO. No hay firma sin autorización.** Todas las `sign_ok` de la auditoría:

| `sign_ok` | Solicitud (id truncado) | Decisión previa | Latencia humana | Revalidación |
|---|---|---|---|---|
| entrada 31 | `iAl6…` | `approved=true`, `reason=humano` | 3,2 s | `ok` |
| entrada 60 | `lepY…` | `approved=true`, `reason=humano` | 3,6 s | `ok` |
| entrada 87 | `Kikz…` | `approved=true`, `reason=humano` | 1,6 s | `ok` |

- Cada `sign_ok` está precedida por `pending_created` y por una `decision` humana de **la misma** solicitud; el contador de firmas de cada sesión coincide (1, 1 y 1 en curso).
- Hubo **7 aprobaciones** (`POST …/approve`: 3 `connect` y 4 `sign_event`) y **0 rechazos**, todas llegadas por **3 conexiones HTTP persistentes** del mismo origen (patrón de un navegador; un script abriría una conexión por petición). Las escrituras del agente fueron solo: 1 login + 1 logout de `check_live.py`, con 3 comprobaciones CSRF (los 3 `403` de `logout`), y la lectura de este diagnóstico: ninguna aprobación.
- Una aprobación humana (`7Of7…`, tras **49 s**) fue **rechazada correctamente por la revalidación P-38** (`politica_incumplida`, `created_at` de 49 s con ventana de 30 s): sin firma y respuesta `unauthorized`.
- La identidad cargada en el firmante es `1df53cc3…` (**no** es la de B4 `c5a035bf…`). El propietario importó identidades por la interfaz (`PUT /api/identity`: 2 correctas y 1 rechazada por inválida).

## 2. Las «respuestas anticipadas» del cliente de laboratorio: error del cliente, no del producto

1. **Primera ejecución** (la única que escribió resumen): la primera firma válida se aprobó a los 49 s y se rechazó (correcto: ventana de 30 s). El cliente envió **de inmediato** la solicitud de la prueba tardía y esperaba que el propietario aprobara tras ≥ 35 s; se aprobó a los 3 s: una aprobación humana **a tiempo** → firma válida. El cliente esperaba un rechazo y lo marcó `FAIL`.
2. **Ejecuciones posteriores:** se aprobó en 1,6 a 3,6 s, **antes** de que terminara la ventana de silencio de 8 s del cliente («ausencia de firma automática»). El cliente recibió la firma temprano, lo interpretó como firma automática y terminó con error (sin escribir resumen). Fue una aprobación humana (decisión `humano` con latencia).
3. Un `connect` extra sin tarjeta (entrada 62): se reutilizó una URI ya consumida; el firmante lo rechazó por ser de un solo uso (comportamiento correcto).

**Defectos del cliente de laboratorio (`lab/manual/local_client.py`):** (a) la prueba «no firma sola» se basa en **tiempo** y choca con una persona que aprueba rápido: la prueba correcta es de **estado** (la solicitud permanece pendiente y sin firma hasta el clic; auditoría `decision` humana antes de `sign_ok`); (b) `reply()` toma el siguiente mensaje del buzón **sin correlacionar por id de solicitud**: podría atribuir la respuesta de una operación a otra; (c) la prueba tardía exige esperar sin ninguna indicación en pantalla; (d) es un script de terminal: contradice la experiencia esperada; (e) solo escribe el resumen si termina todo.

## 3. Observación del producto (no es un defecto de seguridad)

La tarjeta muestra «caduca en N s» según `APPROVAL_TTL_S` (en esta demostración, 90 s), pero el plazo efectivo para **firmar** es `SIGNER_WINDOW_S` (30 s) menos la antigüedad de la plantilla. La demostración usa `APPROVAL_TTL_S` > `SIGNER_WINDOW_S` **a propósito** para poder enseñar la revalidación P-38, pero la interfaz no lo explica (es el límite ya conocido «la cuenta atrás usa `APPROVAL_TTL_S`, no la ventana real» de P-42/B6.1B). Propuesta opcional: mostrar «Firmar antes de N s».

## 4. Qué se puede hacer hoy desde el navegador (sin scripts)

| Operación | Disponible | Evidencia |
|---|---|---|
| Login local | Sí | 4 logins (2 del agente) |
| Crear identidad temporal | Sí | `POST /api/identity` ×2 |
| Importar identidad | Sí | `PUT /api/identity` ×3 (1 inválida rechazada con 400) |
| Iniciar / detener el firmante | Sí | `start` ×4, `stop` ×3 |
| Emitir y copiar la URI bunker | Sí | `POST /api/connections` ×5 |
| Aprobar / rechazar **conexiones** | Sí | 3 aprobadas; rechazo: sin uso manual (cubierto por pruebas automatizadas) |
| Aprobar / rechazar **firmas** | Sí | 4 aprobadas; rechazo: sin uso manual (automatizado) |
| Ver el resultado final | Sí (P-42) | backend: `outcome=signed`; la observación visual del propietario no se ha reportado |
| Logout | Sí | el propietario no llegó a cerrar sesión en esta sesión (los 2 `204` son del agente) |

**Lo que falta no es del firmante:** el producto es el firmante NIP-46 y ya cubre toda la administración desde el navegador. Falta una **aplicación cliente** (la que hace de «Stacker News») que también se use desde el navegador.

## 5. Propuesta técnica mínima: cliente de demostración en el navegador

**Opción recomendada: página + servidor local con el cliente NDK 2.12.2 REAL.** Un pequeño servicio de laboratorio en la imagen existente `nip46-lab-node:1.0a` (ya contiene NDK 2.12.2 y `@noble`, el mismo cliente que usa Stacker News y que ya validamos). La página no hace criptografía: pide operaciones al servicio y muestra su estado. Sin dependencias nuevas, sin imagen nueva, sin tocar `app/`.

```
Pestaña A  http://127.0.0.1:8000   ← firmante (aprobación humana, solo aquí)
Pestaña B  http://127.0.0.1:18080  ← cliente de demostración (servicio Node + NDK real)
                      └─ ws://relay:7777 (relay local del laboratorio)
```

**El cliente permite (todo desde la página):** pegar la URI; conectarse **solo** al relay local de la URI; `connect`; `get_public_key`; `ping`; `sign_event` válido; `sign_event` inválido (origen ajeno, `kind` distinto, método, contenido, edad, reutilización de reto); ver por operación: enviada → esperando aprobación (con contador) → respondida (éxito/error con el motivo) y, para una firma, **«firma recibida y verificada»** (id = plantilla, firma BIP-340 válida, clave = la de `get_public_key`, `kind 27235`, reto y origen esperados).

**Archivos a crear:** `lab/manual/client_web/server.mjs` (servidor `node:http` sin dependencias, NDK real), `index.html`, `app.js`, `app.css`; `tests/e2e/test_manual_client_web.py`; este informe actualizado al cerrar. **A modificar:** `lab/manual/compose.manual.yaml` (servicio `client-web` bajo `profiles: [client]`, puerto `127.0.0.1:18080`, montaje de solo lectura); `README.md` (sección corta «Demostración local desde el navegador»). **No se modifica** `app/`, el `Dockerfile` ni `compose.yaml` del producto (la página no entra en la imagen de producción por defecto). `lab/manual/local_client.py` queda como legado o se retira (a decidir).

**Decisiones que necesito de usted:** (1) usar el cliente NDK real en Node (recomendado) en lugar de un cliente propio en Python; (2) añadir «Firmar antes de N s» a la tarjeta del firmante (cambio pequeño en `app/static`, opcional); (3) parámetros de la demostración: sugiero `SIGNER_WINDOW_S=45` y `APPROVAL_TTL_S=120` (aprobar a tiempo es más cómodo y la prueba tardía exige esperar > 45 s); (4) retirar `local_client.py`.

## 6. Seguridad y aislamiento

| Riesgo | Mitigación |
|---|---|
| La página de laboratorio aprueba por su cuenta | El servicio **no tiene credenciales del firmante**, ni endpoint de aprobación; la aprobación solo existe en la pestaña A (cookie `HttpOnly`, `SameSite=Strict`, CSRF y `Origin` local: otra página no puede usarla). Prueba: desde la pestaña B no hay forma de aprobar |
| Conexión a relays públicos o Stacker News | El servicio rechaza cualquier relay que no sea `relay`/`localhost`/`127.0.0.1`; la URI del firmante ya apunta a `ws://relay:7777`; prueba con `/proc/net/tcp` de los tres contenedores y con intercepción de peticiones del navegador |
| Fuga de la URI o de claves | URI (campo oculto) y claves efímeras solo en memoria del servicio; nunca en logs, DOM persistente, `localStorage`, ni en el resumen; el servicio olvida todo al cerrar la sesión o a los N minutos; el registro redacta |
| Otra página local usa el servicio de la demostración | Escucha solo en `127.0.0.1`; token de sesión aleatorio en memoria; comprobación de `Host`/`Origin`; CSP estricta; sin CORS |
| Identidades reales | Solo identidades efímeras generadas en el momento; el servicio no importa claves; B4 nunca se usa |
| Entra en producción | Vive en `lab/manual/` bajo un perfil de Compose; no está en el `Dockerfile` ni en `compose.yaml` |
| Debilitar políticas | Ninguna política, permiso ni límite del firmante cambia |

## 7. Pruebas necesarias (se comprueba el **contenido**, no solo que haya respuesta)

Automatizadas con Playwright (dos contextos de navegador; los clics de aprobación en la pestaña A los hace la prueba, lo cual es una **prueba automatizada**, distinta de la validación manual del propietario):
1. **Flujo completo:** connect, `get_public_key` (distinta de la clave de transporte), ping, firma válida verificada (id, BIP-340, identidad, kind, reto/origen), y `outcome=signed` en el firmante.
2. **Ausencia de firma automática:** sin clic, la operación permanece «esperando aprobación» y `signatures == 0`; la auditoría muestra la decisión `humano` **antes** de `sign_ok`.
3. **Correlación:** dos `sign_event` simultáneos aprobados en orden inverso; cada resultado se asigna a su solicitud (por id), ninguno se cruza.
4. **Expiraciones:** sin decisión → denegada por `timeout`; aprobación fuera de plazo → «Rechazada al firmar» (revalidación P-38) y el cliente muestra el error.
5. **Reintentos y reconexiones:** reutilizar una URI (de un solo uso) falla; si el relay se reinicia, el cliente muestra la desconexión y no reconecta en silencio (el firmante termina la sesión; hace falta una URI nueva).
6. **Aislamiento:** dos clientes y dos sesiones del firmante no se mezclan; una URI no sirve en otra sesión.
7. **Rechazos por política:** origen ajeno, `kind` distinto, método, contenido, edad excesiva y reutilización del reto: rechazados sin tarjeta.
8. **Sin conexiones externas / sin secretos:** `/proc/net/tcp` sin direcciones públicas en los 3 contenedores; el navegador solo habla con orígenes locales; la URI y las claves no aparecen en registros, DOM ni resumen.
9. **Comprobaciones negativas del cliente:** una respuesta sin firma válida, o con id distinto, **no** puede mostrarse como éxito (prueba con un firmante manipulado que devuelve una firma inválida).

## 8. Tiempo y complejidad

Complejidad **media**: ~350 líneas de servicio y página más ~250 de pruebas, sin dependencias nuevas. Estimación: **0,5 a 1 jornada** de trabajo (varias iteraciones con revisión). Riesgo principal: detalles de la API de NDK 2.12.2 para `ping` y para el manejo de errores/tiempos de espera (se verificará contra el código vendido antes de implementar); riesgo secundario: pruebas con dos pestañas y temporizaciones (se usarán relojes del servidor y estados, no esperas fijas).

## 9. Hallazgo lateral

Las pruebas Docker anteriores (`docker rm -f` sin `-v`) dejaron decenas de **volúmenes anónimos** de Docker (restos de bases de prueba con administradores ficticios). No pertenecen al propietario ni contienen datos reales; no se tocaron. Corrección menor propuesta: usar `docker rm -fv` en esas pruebas.

## 10. Estado actual

La pila de la demostración (proyecto `nip46-manual`: firmante en `127.0.0.1:8000`, relay local en `127.0.0.1:17777`) sigue en ejecución con la identidad efímera `1df53cc3…`; no hay conexiones externas (0 TCP hacia direcciones públicas). Se detiene con `docker compose -p nip46-manual down` (conserva el volumen) o con `down -v` (borra solo la base de prueba).
