# Controlador de la Compuerta B y Compuerta A local operativa (Fase 1.0A.2)

| Campo | Valor |
|---|---|
| Fecha del prompt (UTC) | 2026-11-20T23:13:11.222Z |
| Fase | 1.0A.2 |
| Agente | Claude Code (extensión de VS Code, versión 2.1.329) |
| Modelo | claude-sonnet-5-5 (campo `model` de los registros de sesión) |
| Nivel de razonamiento | high |
| Sesión | 35f0f3c1-13e9-47b9-832f-f6252cd2166f |
| Origen de la transcripción | Archivo de sesión local de Claude Code (JSONL), extraído con script; no reconstruido |
| Estado | COMPLETA (contenido visible) |

**Qué contiene y qué no.** Prompts del propietario (sin las etiquetas `<pasted_content>`, los bloques del editor ni los recordatorios del sistema) y todo el texto visible de las respuestas de Claude Code, en orden y con marca de fecha (UTC). Las llamadas a herramientas se indican con una línea de marcador; **no se incluyen** sus entradas completas, sus resultados, el razonamiento interno ni el contexto del sistema.

**Redacción aplicada** (revisada con escaneo de patrones y lectura directa): URI `bunker://` completas, claves `nsec`, tokens y secretos; el usuario y el nombre del equipo de Windows (`[REDACTADO:usuario-local]`), el correo y el nombre del propietario; las rutas absolutas del proyecto se acortaron a rutas relativas. Los `[REDACTADO:…]` que aparezcan dentro de una respuesta de Claude Code pueden ser texto original (se habla de la convención) o redacciones de esta exportación.

---

## Prompt del propietario (2026-11-20T23:13:11.222Z)

# AUTORIZACIÓN FINAL — FASE 1.0A.2 — COMPUERTA B: STACKER NEWS

El propietario autoriza expresamente ejecutar la Compuerta B para observar la interacción real entre Stacker News y nuestro firmante NIP-46.

La ejecución queda limitada a las condiciones siguientes.

## 1. Ventana autorizada

- Fecha: 2026-11-20.
- Zona horaria: America/Santiago (UTC−03:00).
- Inicio: 20:14:00.
- Fin absoluto: 20:19:00.
- Duración máxima global: 300 segundos, incluida la limpieza.
- No iniciar si la ventana ya expiró.
- No ampliar la ventana ni reintentar sin nueva autorización.

Si el lanzador permite preparar el entorno antes del inicio, puede hacerlo sin conexiones externas. La conexión externa solo puede comenzar dentro de la ventana.

Si no existe un control automático y verificable del límite global, detenerse antes de ejecutar e informar la limitación.

## 2. Destino autorizado

Único relay:

`wss://relay.primal.net:443`

Mantener el proxy restringido exclusivamente a ese host y puerto.

No utilizar `relay.primal.io`, `relay.nsec.app` ni otros relays.

No permitir conexiones externas adicionales desde los contenedores.

La interacción con `https://stacker.news/signup` se realizará exclusivamente desde el navegador del propietario, de forma manual.

## 3. Configuración obligatoria

- `MODE=observe`.
- Aprobación configurada como `tty`.
- Identidad Nostr nueva y desechable, exclusivamente en memoria.
- Cero firmas permitidas.
- Cero preguntas de aprobación de firma.
- Sin puertos publicados.
- Sin secretos en archivos de evidencia.
- TLS verificado.
- `TLS_GROUPS=X25519`, si corresponde al cliente de esta compuerta.

Antes de ejecutar, repetir las verificaciones locales `check-b` y `preflight-b`, siempre sin tráfico externo.

Si alguna falla, NO-GO y detenerse.

## 4. Secuencia de ejecución

1. Verificar la hora de Chile y la ausencia de recursos Docker residuales.
2. Iniciar el firmante exclusivamente dentro de la ventana autorizada.
3. Establecer conexión WSS con `relay.primal.net`.
4. Mostrar al propietario la URI `bunker://` desechable únicamente en la terminal interactiva.
5. Esperar a que el propietario abra manualmente `https://stacker.news/signup`.
6. El propietario ingresará la URI en la interfaz correspondiente.
7. Observar si Stacker News envía una solicitud NIP-46 `connect`.
8. Permitir únicamente la respuesta `ack` prevista para `connect`.
9. Registrar de forma depurada los métodos, parámetros y metadatos observables.
10. Si llega `sign_event`, responder `unauthorized` sin firmar.
11. Detenerse ante cualquier operación que requiera crear una cuenta, aprobar una firma o ampliar los permisos.
12. Terminar la ejecución y limpiar todos los recursos Docker antes del límite absoluto.

No presionar botones en el navegador del propietario.

No automatizar la interacción con Stacker News.

No avanzar en formularios o confirmaciones sin autorización expresa.

## 5. Comportamientos prohibidos

- Firmar cualquier evento, incluido `kind 27235`.
- Crear una cuenta real en Stacker News.
- Completar una autenticación real.
- Responder a desafíos `AUTH` del relay.
- Cambiar de relay.
- Reintentar conexiones.
- Utilizar identidades persistentes.
- Guardar claves privadas o retos de autenticación en claro.
- Ejecutar la Compuerta C.
- Modificar `app/`, dependencias, `AGENTS.md`, `CLAUDE.md` o la estructura de carpetas.
- Hacer commit o push.
- Iniciar la Fase 1.0B.
- Cerrar documentalmente la Fase 1.0A.3.

## 6. Condiciones de parada

Detener inmediatamente si:

- Se detecta un destino externo no autorizado.
- Se solicita una firma que no pueda rechazarse de manera segura.
- La interfaz exige una acción que pueda crear una cuenta.
- Se detecta una configuración distinta de `observe`.
- Se detecta exposición de secretos.
- Aparece una solicitud `AUTH` que requiera autenticación.
- El propietario solicita detener la prueba.
- Se alcanza el límite de tiempo.

Si Stacker News no envía ninguna solicitud, registrar ese resultado. No improvisar pasos adicionales ni reintentar.

## 7. Evidencia

Guardar únicamente evidencia depurada dentro de `lab/results/`, excluida de Git.

Registrar:

- Hora real de inicio y término.
- Estado de la conexión WSS.
- Recepción o ausencia de `connect`.
- Parámetros observados de `connect`, sin secretos.
- Recepción o ausencia de `sign_event`.
- Metadatos estructurales del evento, si aparece.
- Cantidad de firmas realizadas: debe ser cero.
- Cantidad de aprobaciones de firma: debe ser cero.
- Respuestas NIP-46 emitidas.
- Errores y condiciones de parada.
- Resultado del escaneo de secretos.
- Recursos Docker residuales: deben ser cero.

No guardar capturas del navegador salvo autorización adicional.

## 8. Informe final

Entregar:

1. Resultado de conectividad.
2. Si Stacker News reconoció la URI `bunker://`.
3. Si llegó `connect` y qué parámetros se observaron.
4. Si llegó `sign_event` y su estructura.
5. Si apareció el evento `kind 27235`.
6. Si se observó el valor `u`, sin registrar desafíos sensibles.
7. Respuestas emitidas por el firmante.
8. Confirmación de cero firmas y cero cuentas creadas, indicando qué pudo verificarse directamente.
9. Duración total.
10. Estado final de Docker y secretos.
11. Clasificación fundamentada: GO, PARTIAL o NO-GO.
12. Riesgos y próximos pasos para una eventual Compuerta C.

Distinguir evidencia observada, inferencias e hipótesis.

No considerar una respuesta `connect` exitosa como autenticación completa en Stacker News.

## 9. Cierre

Al finalizar, detenerse.

No ejecutar nuevas actividades externas.

Esperar revisión del propietario y ChatGPT antes de cualquier avance.

### Claude Code (2026-11-20T23:13:24.140Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:13:36.595Z)

No ejecuté la Compuerta B: es NO-GO por una limitación que tu autorización pedía respetar. La verifiqué a las 20:13:24 (Chile) y no hice ninguna conexión externa. Docker está en 0 y Git sin cambios nuevos.

## Por qué no se ejecutó

1. **No existe un control automático y verificable del límite global para B.** El lanzador `run_gate_a.py` impone ventana, tope de 300 s y limpieza solo para las sondas A. El procedimiento de B es manual (`docker compose run` y `Ctrl+C`), y el límite de 10 minutos de esa solicitud es un consejo al operador. Tu cláusula pide detenerse en ese caso.

2. **El flujo interactivo no se puede hacer de forma segura desde mi herramienta.**
   - **La URI `bunker://` quedaría en mi salida y en la transcripción.** Es desechable y de un solo uso, pero el requisito era mostrarla únicamente en la terminal interactiva.
   - **No sé que veas la salida de mi herramienta.** Esa salida es para mí, no te llega de forma fiable, así que no podrías verla ni copiarla al navegador.
   - **La aprobación de `connect` necesita stdin interactivo.** Por diseño, el firmante rechaza la aprobación con guion con un relay real, y no puedo teclear `s` por ti.

3. **El tiempo.** Quedaban 35 s para el inicio. Escribir y validar un controlador ahora significaría usar código sin probar dentro de la ventana, y no lo hice.

## Propuesta para una nueva ventana (no ejecutada)

Escribo `run_gate_b.py` y lo pruebo solo en local, con reloj simulado y sin red. Haría lo siguiente:
- impone la ventana y un tope duro de 300 s que mata el proceso y limpia;
- repite `check-b` y `preflight-b` antes de empezar, y aborta si alguno falla;
- arranca el proxy y el firmante con `MODE=observe` fijo;
- **lo ejecutas tú en tu propia terminal de PowerShell**, para que la URI y la pregunta de `connect` aparezcan solo ahí;
- hace la limpieza Docker, guarda la evidencia depurada y escanea secretos.

Después me das una ventana nueva con fecha y hora de Chile. Si prefieres otro modo de operar la parte interactiva, dímelo.

## Mensaje del propietario durante la interacción (2026-11-20T23:16:32.939Z)

# FASE 1.0A.2 — NUEVA COMPUERTA A OPERATIVA Y PREPARACIÓN DE COMPUERTA B

## Contexto

Estamos desarrollando un firmante remoto NIP-46 en Python para validar su interoperabilidad con Stacker News.

Resultados anteriores:

- Interoperabilidad Python/NDK validada en laboratorio.
- NIP-04, NIP-44, connect, get_public_key y sign_event validados localmente.
- Relay público relay.primal.net:443 validado con TCP, TLS, WSS, EOSE, OK y eco.
- Compuerta B con Stacker News no ejecutada debido a limitaciones operativas del controlador y del acceso interactivo.

El propietario decidió realizar primero una nueva Compuerta A de validación operativa y, posteriormente, una Compuerta B real con Stacker News.

## Objetivo

Preparar un controlador seguro y verificable para ejecutar la Compuerta B desde PowerShell, validándolo previamente mediante una nueva Compuerta A local.

No modificar la arquitectura ni reorganizar el repositorio.

## TAREA 1 — Construir run_gate_b.py

Crear `lab/real/run_gate_b.py`, reutilizando los componentes existentes del laboratorio y los controles pertinentes de `run_gate_a.py`.

Requisitos:

1. Ejecutarse desde PowerShell en Windows.
2. Mantener stdin y stdout interactivos para el propietario.
3. Mostrar la URI bunker:// únicamente en la terminal local del propietario.
4. No registrar la URI, secretos ni retos de autenticación en archivos o transcripciones.
5. Permitir la aprobación manual de connect.
6. Mantener MODE=observe y APPROVAL_MODE=tty como valores efectivos, incluso ante variables de entorno hostiles.
7. Prohibir todas las firmas, incluido kind 27235.
8. Utilizar exclusivamente relay.primal.net:443 durante la futura ejecución externa.
9. Aplicar un límite global de 300 segundos, incluida la limpieza.
10. Reservar tiempo para finalizar procesos y limpiar Docker antes del límite absoluto.
11. Permitir interrupción manual anticipada.
12. Garantizar limpieza ante errores y excepciones.
13. Ejecutar check-b y preflight-b antes de cualquier conexión externa.
14. Mantener un único intento, sin reintentos automáticos.
15. No iniciar fuera de una ventana autorizada.

Si no es posible garantizar alguno de estos controles, detenerse e informar la limitación.

## TAREA 2 — Nueva Compuerta A: validación operativa local

Preparar un modo de ensayo completamente local, sin conexiones externas.

Debe utilizar un relay de laboratorio y solicitudes NIP-46 simuladas o generadas por el cliente NDK local.

Comprobar:

- Arranque del controlador desde PowerShell.
- Disponibilidad real de stdin/TTY.
- Visualización de la URI bunker:// en la terminal del propietario.
- Aprobación manual de connect.
- Recepción de solicitudes NIP-46.
- Rechazo de sign_event.
- Cero firmas realizadas.
- Cero cuentas creadas.
- Detención manual.
- Detención automática por tiempo.
- Limpieza Docker.
- Ausencia de secretos en evidencias.

No basta con pruebas simuladas de stdin: preparar una comprobación interactiva real desde PowerShell, utilizando exclusivamente infraestructura local.

La prueba debe ser reproducible y tener criterios explícitos de GO/NO-GO.

## TAREA 3 — Pruebas automatizadas

Agregar pruebas locales para:

- Inicio programado.
- Inicio tardío.
- Vencimiento de ventana.
- Presupuesto de tiempo y limpieza.
- Proceso bloqueado.
- Errores de Docker.
- Interrupción manual.
- Entorno hostil.
- Ausencia de firmas.
- Protección de la URI bunker://.
- Restricción de destinos.
- Un solo intento.
- Ausencia de recursos residuales.

Utilizar relojes simulados, procesos falsos y relays locales cuando corresponda.

No realizar conexiones externas.

## TAREA 4 — Preparación de Compuerta B

Actualizar únicamente el procedimiento de ejecución de la Compuerta B para utilizar el controlador nuevo.

La futura Compuerta B deberá:

- Ejecutarse desde PowerShell del propietario.
- Utilizar relay.primal.net:443.
- Mantener MODE=observe.
- Permitir únicamente connect/ack.
- Rechazar todas las solicitudes sign_event.
- Permitir interacción manual del propietario con https://stacker.news/signup.
- No crear cuentas ni completar autenticaciones.
- No guardar capturas ni secretos.
- Detenerse dentro de una ventana expresamente autorizada.

No ejecutar esta compuerta todavía.

## TAREA 5 — Registro de uso de IA

Mantener la clasificación metodológica:

LAB:
Investigación, pruebas, experimentación, diagnóstico y validación del controlador.

DOC:
Documentación del procedimiento, evidencia y transferencia de hallazgos.

DEV:
Implementación del producto definitivo. No corresponde a esta actividad.

No modificar la arquitectura ni la estructura de carpetas para representar esta clasificación.

No reconstruir tiempos de trabajo no medidos.

No cerrar todavía la Fase 1.0A.3.

## Restricciones obligatorias

- No realizar conexiones externas.
- No acceder a Stacker News.
- No crear cuentas.
- No ejecutar la nueva Compuerta A interactiva sin mi confirmación.
- No ejecutar la Compuerta B.
- No modificar app/, dependencias, AGENTS.md ni CLAUDE.md.
- No hacer commit ni push.
- No iniciar la Fase 1.0B.
- No ampliar el alcance sin aprobación.

## Entregables

Presentar:

1. Archivos creados y modificados.
2. Diseño y funcionamiento del controlador.
3. Comando exacto para ejecutar la nueva Compuerta A desde PowerShell.
4. Comando previsto para la futura Compuerta B.
5. Resultados de pruebas automatizadas y ensayos locales no interactivos.
6. Procedimiento de interacción manual.
7. Criterios GO/NO-GO.
8. Riesgos y limitaciones pendientes.
9. Estado de Git y Docker.
10. Clasificación LAB/DEV/DOC de las actividades.

Detenerse después de preparar y verificar localmente.

No ejecutar ninguna compuerta hasta recibir una nueva autorización expresa.

### Claude Code (2026-11-20T23:17:34.512Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:19:43.433Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:19:51.196Z)

> *[Llamada a herramienta: Edit — lab\py\tests\test_real_signer.py]*

### Claude Code (2026-11-20T23:20:24.697Z)

Ahora el controlador. Lo escribo completo (con dependencias inyectables para poder probarlo con relojes, procesos y Docker falsos).

### Claude Code (2026-11-20T23:21:34.096Z)

> *[Llamada a herramienta: Write — lab\real\run_gate_b.py]*

### Claude Code (2026-11-20T23:22:02.827Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:22:06.962Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:22:10.494Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:23:03.449Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:23:04.963Z)

Ahora las pruebas automatizadas del controlador (relojes, procesos y Docker falsos; sin red).

### Claude Code (2026-11-20T23:24:05.468Z)

> *[Llamada a herramienta: Write — lab\real\test_run_gate_b.py]*

### Claude Code (2026-11-20T23:24:06.287Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:25:04.390Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:25:07.036Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:25:09.944Z)

> *[Llamada a herramienta: Edit — lab\real\test_run_gate_b.py]*

### Claude Code (2026-11-20T23:25:10.618Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:26:07.958Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:26:46.168Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:26:59.120Z)

Estoy ejecutando el ensayo local desatendido de la Compuerta B (escenario `full`: cliente NDK local, relay de laboratorio, stdin simulado). No hay red externa.

### Claude Code (2026-11-20T23:27:01.042Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:27:27.550Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:27:35.347Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:27:37.663Z)

Error mío: el `\n` de JS quedó convertido en salto de línea real al parchear. Lo corrijo.

### Claude Code (2026-11-20T23:27:38.199Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:27:42.377Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:27:56.660Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:28:26.007Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:29:02.132Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:29:56.603Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:32:49.383Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:33:00.035Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:33:51.410Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:34:44.090Z)

> *[Llamada a herramienta: Write — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\35f0f3c1-13e9-47b9-832f-f6252cd2166f\scratchpad\patch_docs.py]*

### Claude Code (2026-11-20T23:34:45.619Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:34:52.876Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:37:43.068Z)

Los tres escenarios desatendidos dan GO con el código final. Verificación final de suites, escaneo independiente, Git y documentación de continuidad.

### Claude Code (2026-11-20T23:37:46.906Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:38:20.915Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:38:24.211Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:38:30.165Z)

> *[Llamada a herramienta: Edit — lab\real\test_run_gate_b.py]*

### Claude Code (2026-11-20T23:38:30.944Z)

> *[Llamada a herramienta: Edit — lab\real\test_run_gate_b.py]*

### Claude Code (2026-11-20T23:38:31.976Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:39:22.735Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:40:14.583Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:40:16.096Z)

Corrigiendo la última prueba (choca con la nueva negativa a reutilizar un directorio de evidencia) y repitiendo las suites.

### Claude Code (2026-11-20T23:40:17.378Z)

> *[Llamada a herramienta: Edit — lab\real\test_run_gate_b.py]*

### Claude Code (2026-11-20T23:40:19.120Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:41:21.100Z)

> *[Llamada a herramienta: Bash]*

### Claude Code (2026-11-20T23:41:42.261Z)

El controlador de la Compuerta B está construido y probado en local. No ejecuté ninguna compuerta, ni hice conexiones externas, ni accedí a Stacker News, ni creé cuentas, ni hice commit o push.

**Falta una comprobación que solo puedes hacer tú:** el ensayo interactivo real en tu PowerShell.

## 1. Archivos
- **Creados:**
  - `lab/real/run_gate_b.py` (el controlador)
  - `lab/real/test_run_gate_b.py` (50 pruebas)
  - `lab/real/test_run_gate_a.py` (14 pruebas)
  - `lab/real/run_gate_a.py`
  - `lab/real/compose.gate-b.yaml`
  - `lab/py/lab_real/tls.py`
  - `lab/py/tests/test_real_guards.py`
- **Modificados:**
  - `lab/py/lab_real/signer.py`: nuevo `RELAY_ATTEMPTS`. El firmante reintentaba la conexión al relay hasta 3 veces, lo que chocaba con "un solo intento".
  - `lab/py/tests/test_real_signer.py`
  - `lab/node/client/main.mjs`: nuevo modo en que el cliente recibe la URI por stdin.
  - `lab/real/compose.rehearsal.yaml`
  - `lab/real/README.md`
  - `lab/real/solicitud-autorizacion-compuerta-B.md`
  - `lab/experiments/definitions-real.md`: nueva sección E12 con los criterios.
  - `docs/ai-sessions/2026-11-20_claude-code_fase-1.0A.2_04-continuidad.md`
  - Sin tocar: `app/`, dependencias, `AGENTS.md`, `CLAUDE.md`.

## 2. Diseño del controlador
- **Terminal real:** exige stdin y stdout reales. Lanzado desde mi herramienta termina en NO-GO antes de tocar Docker, así que yo no puedo ejecutarlo.
- **URI:** pasa solo por la memoria del controlador hacia tu pantalla. No va a archivos, argumentos ni registros. El controlador reenvía tus respuestas al firmante, con máximo 5 líneas cortas.
- **Ventana:** global de 300 s. No inicia pasado inicio+60 s. La observación termina en inicio+260 s y los últimos 40 s se reservan para detener y limpiar.
- **Prechecks:** `check-b` y `preflight-b`, siempre locales, antes de cualquier conexión.
- **Parada manual:** `Ctrl+C` detiene y limpia.
- **Vigilancia:** cada 0,5 s revisa firma, aprobación de firma, modo distinto de `observe`, destino distinto del autorizado y segundo intento de conexión. Si ocurre alguno, parada inmediata.
- **Limpieza:** siempre mata procesos, guarda el log del proxy (solo host:puerto), ejecuta `down -v --remove-orphans`, fuerza limpieza por etiqueta si quedan recursos, escanea secretos y escribe `run_meta_b.json`.
- **Evidencia y firmante:**
  - Se niega a empezar si el directorio de evidencia ya tiene datos.
  - El firmante hace un solo intento de conexión.
  - Los TTL quedan acotados.
  - `MODE`, el modo de aprobación, el guion y `URI_FILE` van fijos en el override de la Compuerta B, así que una variable olvidada en tu sesión no los anula.

## 3. Comando de la nueva Compuerta A (local, interactiva, la ejecutas tú)
```powershell
python -X utf8 lab/real/run_gate_b.py rehearsal --interactive --scenario full
```
Hace prechecks, espera unos 30 s y muestra la URI en tu terminal. Un cliente NDK local se conecta; escribe `s` y Enter para aprobar `connect`. Después el controlador termina, limpia y te pregunta si viste la URI. Variantes de parada, también interactivas:
```powershell
python -X utf8 lab/real/run_gate_b.py rehearsal --interactive --scenario manual-stop   # pulsa Ctrl+C al ver "Observacion activa"
python -X utf8 lab/real/run_gate_b.py rehearsal --interactive --scenario timeout       # no toques nada
```

## 4. Comando previsto de la Compuerta B (solo con nueva autorización)
```powershell
python -X utf8 lab/real/run_gate_b.py run --tls-groups X25519 --start 2026-MM-DDTHH:MM:00-03:00 --evidence-dir lab/results/gate-b-run
```
Va fijado a `relay.primal.net:443` y lo ejecutas tú en tu PowerShell.

## 5. Resultados
- **Pruebas:**
  - `unittest` del laboratorio: 119 OK.
  - Lanzador A: 14 OK.
  - Controlador B: 50 OK.
  - `pytest`: 5 OK.
  - `check`: PASS.
- **Cobertura del controlador:** inicio programado, tardío y vencido; presupuesto y limpieza; proceso bloqueado; errores de Docker; interrupciones; entorno hostil; cero firmas; protección de la URI; destinos y un solo intento; cero residuos. Se probó con reloj, procesos y Docker falsos.
- **Ensayos locales desatendidos** (NDK 2.12.2 y entorno hostil; no sustituyen al interactivo):

| Escenario | Veredicto | Fin de la observación | Duración | Detalle |
|---|---|---|---|---|
| `full` | GO | `cliente_termino` | 14,2 s | 11 firmas denegadas, 0 firmas, `connect` aprobado, URI una vez |
| `manual-stop` | GO | `interrupcion_manual` | 9,7 s | parada manual simulada con CTRL_BREAK |
| `timeout` | GO | `tiempo` | 50,4 s | ventana de 60 s, dentro del límite |

- **Docker y evidencia:** 0 contenedores, 0 redes y 0 volúmenes tras cada ensayo. El escaneo de secretos dio 0 coincidencias, incluida una verificación independiente.
- **Defectos míos corregidos durante el ensayo:** un `\n` de JavaScript convertido en salto de línea real en `main.mjs`; un mínimo de 90 s que abortaba ventanas de 60 s; y la reutilización de un directorio de evidencia que mezclaba dos ejecuciones. Todos están declarados en E12.

## 6. Procedimiento de interacción manual
Está en la sección 4 de `solicitud-autorizacion-compuerta-B.md` (pasos de Stacker News) y en la sección 7 (el ensayo local interactivo). En B, el firmante imprime la estructura de `sign_event` y la deniega solo, sin preguntar.

## 7. Criterios GO/NO-GO
Son 17 criterios en E12, codificados en el evaluador. Cada violación (firma, URI repetida, residuo Docker, fuera de ventana, etc.) invierte el veredicto a NO-GO por su propio criterio, comprobado con pruebas de mutación. La variante interactiva exige además terminal real y tu confirmación de haber visto la URI.

## 8. Riesgos y limitaciones
- **No verificado, solo tú puedes:** la terminal real, la lectura de teclado desde un hilo, el `Ctrl+C` real y la confirmación visual de la URI. Los ensayos desatendidos usan stdin simulado.
- **Contenedor sin pseudo-TTY:** el firmante corre con `-T` y las respuestas viajan por el controlador. Funciona en el ensayo y hace falta confirmarlo en tu consola.
- **Aprobación de `connect`:** es manual y depende de ti. Lo que haga Stacker News sigue siendo hipótesis hasta B.
- **Límite de limpieza:** si Docker tardara más de la reserva, el controlador lo reporta como fuera de ventana en lugar de ocultarlo.
- **Windows:** la parada manual desatendida usa CTRL_BREAK, que solo existe en Windows.

## 9. Estado de Git y Docker
`git diff --check` limpio. Los archivos nuevos los revisé a mano: sin espacios finales, sin CRLF, con salto de línea final. No hay commits, y siguen sin seguimiento los mismos archivos modificados o nuevos bajo `lab/` y `docs/`. Docker está en 0/0/0.

## 10. Clasificación LAB/DEV/DOC
- **LAB:** controlador, pruebas, ensayos y diagnóstico (incluido el hallazgo de los reintentos del firmante).
- **DOC:** procedimiento, criterios E12 y la nota de continuidad.
- **DEV:** ninguno. El firmante y el controlador son código de laboratorio, no el producto.

No registré duraciones de trabajo, y no cerré 1.0A.3.

Me detengo hasta recibir tu confirmación para el ensayo interactivo y, después, una autorización expresa para la Compuerta B.
