# Interacción 26: cierre formal de la Fase 1.0A, Bloques B0 y B1 y propuesta de B2

| Campo | Valor |
|---|---|
| Fecha del primer prompt (UTC) | 2026-11-21T00:26:28.005Z (America/Santiago = UTC-3) |
| Fase | 1.0B |
| Agente | Claude Code (extensión de VS Code, versión 2.1.329) |
| Modelo | claude-sonnet-5-5 (campo `model` de los registros de sesión) |
| Nivel de razonamiento | high (campo `effort` de los registros de sesión) |
| Sesión | 35f0f3c1-13e9-47b9-832f-f6252cd2166f |
| Origen de la transcripción | Archivo de sesión local de Claude Code (JSONL), extraído con script; no reconstruido |
| Estado | COMPLETA (contenido visible) |

**Qué contiene y qué no.** Prompts del propietario (sin las etiquetas `<pasted_content>`, los bloques del editor ni los recordatorios del sistema) y todo el texto visible de las respuestas de Claude Code, en orden. Las llamadas a herramientas se indican con una línea de marcador; su contenido y sus salidas **no** se incluyen (los archivos resultantes están en el repositorio y los resultados de las pruebas, en `docs/decisions.md`). **No se incluye razonamiento interno del modelo** ni contexto del sistema. Las marcas `<!-- fecha -->` son del archivo de sesión.

**Redacción aplicada** (patrones y lectura de los hallazgos): URI `bunker://`, claves `nsec`, secretos de conexión, JWT, tokens `Bearer` y códigos de acceso; el usuario local, el nombre del autor y los correos; la ruta absoluta del proyecto se acortó a ruta relativa. **No hay clave privada de la identidad de B4 en este archivo**: el agente nunca la vio. La clave **pública** de B4 no es secreta y se conserva.

---

## Prompt del propietario (2026-11-21T00:26:28.005Z)

Actúa como ingeniero de software senior especializado en Python, criptografía Nostr, NIP-46, arquitectura de aplicaciones y desarrollo seguro.

Estamos desarrollando el proyecto **Nostr NIP-46 Remote Signer**, cuyo objetivo final es implementar una aplicación mínima, con frontend y API en Python, que permita a cualquier usuario gestionar una identidad Nostr y autenticarse realmente en Stacker News mediante nuestro propio firmante NIP-46.

El proyecto forma parte de una evaluación técnica. Debemos priorizar funcionalidad, seguridad, simplicidad, pruebas reproducibles y trazabilidad del trabajo realizado con IA.

# AUTORIZACIÓN Y ALCANCE

Autorizo:

1. Formalizar el cierre técnico y documental de la Fase 1.0A.
2. Implementar el Bloque B0 de la Fase 1.0B.
3. Implementar el Bloque B1 de la Fase 1.0B.
4. Ejecutar pruebas locales automatizadas y comprobaciones Docker necesarias.
5. Actualizar documentación y registros de IA.
6. Preparar una propuesta para B2.

NO autorizo implementar B2, B3, B4, B5 ni B6.

No hagas commit ni push. Yo realizaré esas operaciones después de revisar los resultados.

# 1. REVISIÓN OBLIGATORIA

Antes de modificar archivos, lee:

- AGENTS.md
- CLAUDE.md
- docs/project-context.md
- docs/decisions.md
- docs/phase-1.0A-closure.md
- docs/phase-1.0B-proposal.md
- docs/nip46-security-design.md
- docs/nip46-implementation-plan.md

Revisa además el código y las pruebas relevantes del laboratorio.

Respeta las decisiones existentes, salvo aquellas expresamente modificadas por este encargo.

Si encuentras contradicciones importantes, infórmalas y detente antes de realizar cambios incompatibles.

# 2. CIERRE DE FASE 1.0A

Apruebo el cierre técnico de la Fase 1.0A con observaciones.

La evidencia demuestra interoperabilidad real con Stacker News, pero NO demuestra todavía un inicio de sesión completo.

Registra correctamente:

- Compuerta A: primer intento NO-GO (16/17), segundo intento GO (17/17).
- Compuerta B: recepción real de connect, get_public_key y sign_event desde Stacker News.
- Evento de autenticación kind 27235.
- Política de validación sin fallos.
- Cero firmas realizadas.
- Ejecución dentro de la ventana autorizada.
- Limpieza Docker completada.
- Ausencia de session_end como limitación documentada.
- Ausencia de veredicto automático de la Compuerta B.
- Autenticación real pendiente para B4/B6.

No repitas ninguna compuerta.

Conserva las evidencias originales.

Mantén lab/results/ excluido de Git y prepara un resumen sanitizado de los resultados relevantes.

Conserva lab/ como laboratorio y arnés de regresión, separado del producto.

Autorizo exportar las transcripciones pendientes de la Fase 1.0A, siempre que se revisen y eliminen secretos, tokens, claves privadas y URI bunker:// completas.

No incorpores las pruebas exploratorias manuales de conectividad realizadas en Windows al registro de iteraciones.

# 3. DECISIONES ARQUITECTÓNICAS APROBADAS

D-1. Dependencias

Utilizar las versiones verificadas en el laboratorio:

- coincurve==21.0.0
- cryptography==50.0.2
- websockets==17.4

Comprobar compatibilidad y registrar cualquier problema antes de introducir alternativas.

D-2. Configuración

Utilizar un único módulo app/config.py para configuración mediante variables de entorno.

D-3. Persistencia

La clave privada Nostr se mantendrá exclusivamente en memoria durante el MVP.

No implementar SQLite, almacenamiento cifrado ni persistencia de identidades.

D-4. Autenticación de API

Utilizar un token de operador aleatorio, generado al iniciar la aplicación, para proteger operaciones sensibles.

No implementar JWT ni un sistema de usuarios.

La implementación de esta autenticación corresponde a B3; durante B0/B1 solo registrar y preparar la decisión arquitectónica.

D-5. Stacker News

Queda pendiente decidir qué identidad se utilizará en la demostración real.

No crear cuentas ni realizar autenticaciones reales durante B0/B1.

D-6. Docker

Mantener Python 3.12 y preparar el bloqueo verificable de la imagen base mediante digest antes de las pruebas reales.

D-7. Relay y TLS

Mantener como relay de referencia:

wss://relay.primal.net

Conservar verificación TLS y la opción X25519 validada en laboratorio.

No conectarse al relay durante este encargo.

# 4. REQUISITO TRANSVERSAL: PORTABILIDAD

La aplicación NO debe quedar vinculada a mi computador.

Debe poder ser clonada, instalada y ejecutada por cualquier usuario en un equipo compatible, incluyendo Windows, Linux o macOS, directamente o mediante Docker cuando esté disponible.

Requisitos:

- No utilizar rutas absolutas personales.
- No depender de mi usuario de Windows.
- No incorporar IP particulares ni configuraciones exclusivas de mi entorno.
- Utilizar rutas relativas y variables de entorno.
- Cada instalación tendrá su propia identidad Nostr, configuración y firmante.
- El frontend, la API y el firmante se ejecutarán como componentes de la misma instancia.
- La aplicación debe poder utilizarse desde el navegador del equipo donde se ejecuta.
- Por defecto, no se debe exponer la API a Internet.
- En Docker, distinguir entre 0.0.0.0 dentro del contenedor y 127.0.0.1 como dirección de publicación en el host.
- No colocar tokens de operador ni secretos en archivos JavaScript públicos.
- Documentar instalación reproducible para terceros.

Esta decisión NO implica implementar un servicio multiusuario, acceso remoto o despliegue público.

# 5. BLOQUE B0 — DECISIONES Y DEPENDENCIAS

Implementa únicamente lo necesario para dejar preparadas las dependencias y la configuración.

Actividades:

1. Registrar las decisiones aprobadas en docs/decisions.md.
2. Actualizar constraints.txt.
3. Verificar compatibilidad con las dependencias existentes.
4. Ejecutar pip check.
5. Verificar construcción Docker.
6. Ejecutar las pruebas existentes.
7. Mantener una configuración mínima y segura.
8. Documentar cualquier limitación o incompatibilidad.

No incorporar dependencias adicionales sin una justificación técnica concreta.

# 6. BLOQUE B1 — NÚCLEO NOSTR

Implementa los módulos del núcleo en app/nostr/:

- keys.py
- event.py
- nip44.py
- nip04.py
- nip46.py

Utiliza como referencia el código criptográfico y los comportamientos ya verificados en el laboratorio.

No hagas que app/ importe módulos de lab/.

Requisitos:

## Identidad Nostr

- Crear claves Nostr.
- Importar claves privadas hex o nsec.
- Validar estrictamente entradas.
- Calcular clave pública.
- Firmar y verificar mediante Schnorr/BIP-340.
- Evitar exposición de secretos en repr, str, excepciones y registros.

## Eventos NIP-01

- Serialización canónica.
- Cálculo y validación de id.
- Firma y verificación.
- Manejo correcto de caracteres escapados.
- Rechazo de eventos malformados.

## NIP-44

- Implementación compatible con NIP-44 v2.
- Vectores oficiales válidos e inválidos.
- Validación de longitudes y entradas.
- Manejo seguro de errores criptográficos.

## NIP-04

- Soporte únicamente para descifrar solicitudes entrantes.
- No utilizar NIP-04 para cifrar respuestas.
- Pruebas de compatibilidad con lo observado en el laboratorio.

## NIP-46

- Modelos estrictos de solicitudes y respuestas.
- Construcción y validación de URI bunker://.
- Relay obligatorio.
- Secreto aleatorio de conexión de al menos 128 bits.
- Validación de parámetros y errores.
- Sin implementar todavía conexiones externas ni el servicio firmante completo.

## Calidad

- Tipado completo.
- Errores de dominio.
- Sin dependencias de FastAPI en el núcleo.
- Sin secretos en registros.
- Pruebas deterministas.
- Cobertura de rutas de error.
- Código mínimo y mantenible.

# 7. CRITERIOS DE ACEPTACIÓN

Antes de considerar completados B0 y B1:

1. Las decisiones aprobadas están registradas.
2. Las dependencias están verificadas.
3. pip check no presenta conflictos.
4. Docker construye correctamente.
5. Las pruebas existentes continúan pasando.
6. Los vectores oficiales BIP-340 y NIP-44 válidos e inválidos pasan.
7. Las pruebas de serialización NIP-01 pasan.
8. Las pruebas de NIP-04 entrante pasan.
9. La gestión de claves hex/nsec funciona.
10. La generación y validación de bunker:// funciona.
11. Las rutas de error están cubiertas.
12. No se exponen secretos.
13. git diff --check está limpio.
14. app/ no depende de lab/.
15. No se realizaron conexiones externas.

Si algún criterio falla, informa el problema y no declares el bloque como completado.

# 8. RESTRICCIONES OPERATIVAS

No abrir Stacker News.

No conectar a relays públicos.

No crear cuentas reales.

No ejecutar nuevas compuertas.

No firmar solicitudes externas.

No modificar el comportamiento del laboratorio salvo una corrección estrictamente necesaria y previamente informada.

No agregar funcionalidades ajenas al alcance.

No hacer commit ni push.

No eliminar evidencias.

No incorporar secretos en archivos versionables.

No avanzar automáticamente a B2.

# 9. DOCUMENTACIÓN Y REGISTRO DE IA

Actualizar:

- docs/project-context.md
- docs/decisions.md
- docs/ai-log.md
- Documentación técnica afectada.
- Transcripciones autorizadas de la Fase 1.0A.

Mantener clasificación LAB / DEV / DOC.

Registrar decisiones, pruebas, resultados, problemas y uso de IA de manera fiel.

No inventar tiempos ni resultados.

# 10. ENTREGA FINAL

Al terminar, presenta un informe con:

1. Cierre formal de 1.0A.
2. Decisiones arquitectónicas registradas.
3. Resumen de implementación B0.
4. Resumen de implementación B1.
5. Archivos creados y modificados.
6. Pruebas ejecutadas, comandos y resultados.
7. Estado de Docker y dependencias.
8. Revisión de seguridad y secretos.
9. Estado de Git, sin commit ni push.
10. Riesgos y pendientes.
11. Propuesta del Bloque B2, sin implementarlo.

Detente después de entregar el informe.

El objetivo es dejar el núcleo Nostr funcional, seguro, probado y portable, preparado para implementar el firmante NIP-46 real en el siguiente bloque.

<!-- 2026-11-21T00:27:25.426Z -->
Empiezo por la revisión obligatoria: estado del repositorio, código/pruebas del laboratorio reutilizables, Dockerfile/compose/README y entorno local.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:29:30.374Z -->
B0, paso 1: añado las tres dependencias aprobadas a `pyproject.toml` y genero la resolución en un entorno temporal limpio (fuera del repositorio).

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — lab/tools/gen_core_fixtures.mjs]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:32:44.490Z -->
Fixtures generados con la misma biblioteca que usa Stacker News. Ahora escribo el núcleo `app/nostr/` (errores, claves con NIP-19, eventos NIP-01, NIP-44, NIP-04 entrante, NIP-46) y `app/config.py`.

> *[Llamada a herramienta: Write — app/nostr/__init__.py]*

> *[Llamada a herramienta: Write — app/nostr/errors.py]*

> *[Llamada a herramienta: Write — app/nostr/keys.py]*

> *[Llamada a herramienta: Write — app/nostr/event.py]*

> *[Llamada a herramienta: Write — app/nostr/nip44.py]*

> *[Llamada a herramienta: Write — app/nostr/nip04.py]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — app/nostr/nip46.py]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:34:44.448Z -->
Escribo las pruebas del núcleo (vectores oficiales, fixtures de `nostr-tools`, rutas de error, secretos y arquitectura).

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — tests/nostr/test_keys.py]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:35:51.322Z -->
Una prueba detectó un defecto real: en Python `$` acepta un salto de línea final (`"…01\n"` pasaba como clave válida). Corrijo todas las expresiones regulares con `\Z`.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:36:04.361Z -->
Ahora las pruebas de eventos, NIP-44, NIP-04, NIP-46, configuración y arquitectura.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — tests/nostr/test_event.py]*

> *[Llamada a herramienta: Write — tests/nostr/test_nip44.py]*

> *[Llamada a herramienta: Write — tests/nostr/test_nip04.py]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Edit — tests/nostr/test_nip44.py]*

> *[Llamada a herramienta: Edit — tests/nostr/test_nip44.py]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — tests/nostr/test_nip46.py]*

> *[Llamada a herramienta: Write — tests/test_config.py]*

> *[Llamada a herramienta: Write — tests/test_architecture.py]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:39:43.510Z -->
Pruebo también en Linux (portabilidad) dentro de un contenedor temporal, instalando con `constraints.txt` como lo haría un tercero.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:40:42.474Z -->
Código y pruebas listos. Paso a la documentación: leo el README actual para actualizarlo (instalación portable y estado).

> *[Llamada a herramienta: Read — README.md]*

> *[Llamada a herramienta: Write — README.md]*

<!-- 2026-11-21T00:41:31.968Z -->
Genero el resumen sanitizado de la evidencia (con hashes SHA-256 de los archivos originales, que permanecen en `lab/results/`).

> *[Llamada a herramienta: Write — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/make_summary.py]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/decisions_b0b1.md]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/b2_proposal.md]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:43:44.005Z -->
Ahora la exportación autorizada de transcripciones: primero inspecciono el formato real del archivo de sesión.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/export_1_0A.py]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:45:18.749Z -->
Exportación generada en un directorio temporal. Reviso con escaneo de patrones sensibles antes de copiarla al repositorio.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/patch_ailog.py]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:46:33.725Z -->
Termino los ajustes del registro de IA (estado de transcripciones y rótulos) y luego hago la verificación final completa.

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:46:51.794Z -->
Verificación final completa de todos los criterios de aceptación.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T00:47:40.901Z -->
B0 está completo y B1 está implementado, pero **no declaro B1 completado**: el criterio 6 (vectores oficiales BIP-340) queda cumplido solo en parte. No hubo conexiones a relays ni a Stacker News, no abrí Stacker News, no firmé nada externo, no toqué `AGENTS.md`/`CLAUDE.md`, no borré evidencias y no hice commit ni push.

## Qué falta para declarar B1 completado
- **BIP-340 parcial:** solo están verificados los vectores 0 a 3. Los transcribí y los comprobé por cálculo con `coincurve`; coinciden clave pública, firma y verificación. El CSV oficial completo (con los negativos de verificación) no se pudo obtener sin conectarme. El ejecutor del CSV está implementado y probado con uno sintético; se activa con `BIP340_CSV_PATH`. Necesito que aportes el CSV, o que autorices una descarga puntual, o que aceptes la excepción.
- **Criterio 15, "sin conexiones externas":** solo se descargaron paquetes del índice público de PyPI (`pypi.org` y `files.pythonhosted.org`), inherente a B0. No hubo relays ni otros servicios. Lo cumplo bajo esa interpretación; confírmala. Los fixtures de `nostr-tools` los generé con Node `--network none`.

## 1. Cierre formal de la Fase 1.0A
Quedó registrado como aprobado con observaciones en `docs/phase-1.0A-closure.md`, `docs/decisions.md` (O-14 y O-15) y el registro de IA.
- **Resumen sanitizado:** `docs/phase-1.0A-evidence-summary.md`, con el SHA-256 de cada original. `lab/results/` sigue excluido de Git.
- **Transcripciones exportadas** y redactadas: ocho nuevas, más la `1.0A_03` reexportada completa (era parcial y la sustituye). Escaneo sin coincidencias de URI, `nsec`, tokens, usuario, correo ni nombre.
- **Siguen pendientes** la de esta interacción (26) y las que ya lo estaban de fases anteriores.
- **Matriz E12:** va en el cierre, §2.3.

## 2. Decisiones registradas
Todas en `docs/decisions.md`:
- D-1 (dependencias), D-2 (`app/config.py`), D-3 (clave solo en memoria), D-4 (token de operador, sin JWT), D-6 (digest preparado), D-7 (relay y TLS) y el requisito de portabilidad.
- D-5 sigue pendiente.
- **Contradicción:** D-4 choca con `AGENTS.md` §3/§7 (JWT). Prevalece tu instrucción, `AGENTS.md` quedó sin tocar, y quedó anotado como P-31. También quité "JWT" de la primera línea del README.

## 3. B0
- **Dependencias:** `coincurve==21.0.0`, `cryptography==50.0.2` y `websockets==17.4`, más `cffi==2.1.1` y `pycparser==3.12`. `certifi` se conservó en la versión previa.
- **Config y Docker:** `app/config.py` con `RELAY_URL` y `RELAY_TLS_GROUPS`, `.env.example`, y `PYTHON_IMAGE` como argumento en el Dockerfile. El digest preparado es el del índice multiarquitectura ya verificado en el laboratorio; no está activado por defecto.
- **Verificación:** `pip check` limpio, `constraints.txt` idéntico a `pip freeze`, 5 pruebas previas OK, imagen construida, contenedor `healthy` y `/health` 200.

## 4. B1
- **Módulos:** `app/nostr/{keys,event,nip44,nip04,nip46}.py`, más `errors.py` (añadido para evitar duplicar y las importaciones circulares).
  - **Keypair:** opaco; no hay forma pública de leer la clave y bloquea `pickle` y `copy`. Importa hex y `nsec` (NIP-19).
  - **Eventos y cifrado:** eventos NIP-01 estrictos; NIP-44 v2; NIP-04 solo descifra (no tiene función de cifrado).
  - **NIP-46:** mensajes y URI `bunker://` con relay obligatorio y secreto de 128 bits.
- **Y-9 validada:** la serialización coincide con `JSON.stringify` de Node 22 en 180 casos.
- **Defecto real corregido:** las pruebas detectaron que las regex con `$` aceptaban un salto de línea final. Corregí con `\Z` y hay pruebas de regresión.

## 5. Archivos
- **Nuevos:** `app/config.py`, `app/nostr/*`, `tests/nostr/*` (con fixtures), `tests/test_config.py`, `tests/test_architecture.py`, `lab/tools/gen_core_fixtures.mjs`, `docs/phase-1.0A-evidence-summary.md`.
- **Modificados:** `pyproject.toml`, `constraints.txt`, `Dockerfile`, `compose.yaml`, `.env.example`, `README.md` (reescrito portable), `docs/decisions.md`, `docs/ai-log.md` (entrada 26), `docs/phase-1.0A-closure.md`, `docs/phase-1.0B-proposal.md`, `docs/project-context.md` y la nota de continuidad.

## 6. Pruebas
- `python -m pytest -q`: **253 passed, 1 skipped** (el CSV BIP-340 omitido con aviso visible).
- Los vectores NIP-44 oficiales se leen del archivo local y verifican su SHA-256; con el archivo presente pasan todos, válidos e inválidos.
- La misma suite pasa en Linux, en un contenedor con Python 3.12.16 e instalando con `constraints.txt`.
- Con herramientas temporales fuera de las dependencias del proyecto:
  - `mypy --strict`: sin incidencias.
  - `coverage` de líneas y ramas: 100 % del código de `app/`.

## 7. Docker y dependencias
- El digest es del índice multiarquitectura de `python:3.12.16-slim-trixie`.
- La construcción con la etiqueta mutable por defecto no se ejecutó, porque habría consultado el registro de imágenes.
- Al terminar: 0 contenedores, 0 redes y 0 volúmenes.

## 8. Seguridad y secretos
- `app/` no importa `lab/`; el núcleo no importa FastAPI ni hace E/S. Una prueba de arquitectura lo vigila.
- Los hallazgos del escaneo son claves de juguete (`0x…01` a `0x…03`), vectores públicos del NIP-19 y de BIP-340, y patrones de búsqueda en marcadores de transcripciones. Ninguna es una clave real.
- No hay rutas, IP ni usuario propios en lo versionable.

## 9. Git
`git diff --check` limpio, y revisé a mano que los archivos nuevos no tengan espacios finales ni CRLF. Sin commits (HEAD sigue en `ec739bd`). Todo el trabajo de 1.0A y 1.0B queda sin versionar para que lo hagas tú.

## 10. Riesgos y pendientes
- BIP-340 parcial y D-5.
- Decidir si se versiona `lab/`.
- Decidir si `mypy` y `ruff` pasan a ser dependencias de desarrollo.
- No hay hashes en `constraints.txt`.
- Antes de las pruebas reales hay que activar el digest.

## 11. Propuesta del Bloque B2 (sin implementar)
Detalle completo en `docs/phase-1.0B-proposal.md` §9: un firmante NIP-46 en proceso, sin API ni interfaz.
- **B2a:** política `27235` (reutiliza `lab_real/policy.py`), conexiones y solicitudes pendientes.
- **B2b:** `SignerService` con respuesta siempre en NIP-44, auditoría con lista blanca y cierre ordenado que deja evidencia de `session_end`, lo que cierra F-2.
- **B2c:** cliente de relay con un intento, TLS verificado y detención ante `AUTH`.
- **B2d:** regresión con NDK 2.12.2 contra un relay local, E1–E3 y la variante de E8, sin red externa.
- **Decisiones B2-1 a B2-7:** la más importante es permitir E/S de red solo en `relay.py`, lo que exige actualizar la prueba de arquitectura.
- **Criterios:** 10, incluido ≥95 % de cobertura del código nuevo y `mypy --strict` limpio.

Me detengo aquí a la espera de tu decisión sobre BIP-340 y de tu autorización para B2.
