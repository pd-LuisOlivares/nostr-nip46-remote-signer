# Interacción 55: Auditoría final de cumplimiento y cierre documental acotado (README, ChatGPT, procedimiento de cierre)

| Campo | Valor |
|---|---|
| Fecha del primer prompt (UTC) | 2026-11-22T13:07:31.955Z (America/Santiago = UTC-3) |
| Fase | 1.0B |
| Agente | Claude Code (extensión de VS Code, versión 2.1.330) |
| Modelo | claude-sonnet-5-5 (campo `model` de los registros de sesión) |
| Nivel de razonamiento | high (campo `effort` de los registros de sesión) |
| Sesión | 97ea8763-694e-4b53-8496-52b85c37bc64 |
| Origen de la transcripción | Archivo de sesión local de Claude Code (JSONL), extraído con `tools/ai_sessions.py`; no reconstruido |
| Hasta (UTC) | 2026-11-22T13:21:10.494Z |
| Estado | PARCIAL (la sesión de origen permanecía abierta al momento de la exportación) |

**Qué contiene y qué no.** Prompts del propietario (sin las etiquetas `pasted_content`, los bloques del editor ni los recordatorios del sistema) y todo el texto visible de las respuestas de Claude Code, en orden. Las llamadas a herramientas se indican con una línea de marcador; su contenido y sus salidas **no** se incluyen (los archivos resultantes están en el repositorio y los resultados de las pruebas, en `docs/decisions.md`). **No se incluye razonamiento interno del modelo** ni contexto del sistema. Las marcas `<!-- fecha -->` son del archivo de sesión.

**Redacción aplicada** (patrones y lectura de los hallazgos): URI `bunker://`, claves `nsec`, secretos de conexión, JWT, tokens `Bearer`, hashes de contraseña, contraseñas, correos, rutas locales, usuario local y nombre del autor. Las cadenas hexadecimales de 64 caracteres se clasifican por contexto: se conservan las claves **públicas**, los identificadores y las huellas SHA-256 necesarios para entender la evidencia (revisadas una a una) y la exportación se detiene ante cualquier duda. La ruta absoluta del proyecto se acortó a ruta relativa. Redacciones en este archivo: ruta-del-proyecto: 1, usuario-local: 2.

---

## Prompt del propietario (2026-11-22T13:07:31.955Z)

Actúa como auditor técnico de entrega de una prueba de desarrollo.

**Contexto:** repositorio `pd-[REDACTADO:usuario-local]livares/nostr-nip46-remote-signer`, rama `main`. La prueba original solicita una aplicación mínima en Python, Rust, Elixir o Go que permita crear o ingresar una clave secreta Nostr, utilizar un firmante NIP-46 propio y demostrar autenticación real en Stacker News. Exige README breve, supuestos, tradeoffs y registros de conversaciones con IA.

**Objetivo:** realizar una auditoría final de cumplimiento y preparar un cierre documental mínimo.

### Alcance autorizado

1. Verificar que el repositorio publicado coincide con el estado local esperado. Reportar commit, rama y cambios pendientes.
2. Revisar que el README permita a un evaluador ejecutar la aplicación desde un clon limpio, sin depender de archivos locales privados.
3. Comprobar el estado de las transcripciones de IA, especialmente las interacciones 40 a 54, identificando las parciales, incompletas o pendientes.
4. Ejecutar `python tools/ai_sessions.py check` y reportar el resultado real.
5. Revisar la evidencia existente de autenticación real en Stacker News. No repetir conexiones externas ni inventar capturas o resultados.
6. Identificar si la documentación comunica adecuadamente la decisión de alcance: solución mínima funcional, límites deliberados y funcionalidades adicionales justificadas.
7. Entregar una matriz de cumplimiento con estados CUMPLE, PARCIAL, NO CUMPLE y NO VERIFICADO.

### Restricciones

- No modificar código funcional.
- No cambiar Docker, SQLite, identidades Nostr, credenciales ni volúmenes.
- No ejecutar `git commit`, `git push`, `git reset`, `git clean` ni operaciones destructivas.
- No establecer conexiones con Stacker News ni relays públicos.
- No imprimir secretos ni transcripciones sin redactar.
- No ampliar funcionalidades.
- Proponer solamente correcciones documentales imprescindibles, sin aplicarlas hasta mi autorización.

**Resultado esperado:** informe conciso con hallazgos clasificados por severidad, evidencia verificable, riesgos reales para la evaluación y propuesta de acciones mínimas para dejar la entrega lista.

<!-- 2026-11-22T13:07:36.939Z -->
Auditoría de solo lectura. Empiezo por el estado de Git y el remoto, la trazabilidad y los contenidos que exige la prueba.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T13:09:09.422Z -->
## Informe de auditoría final (solo lectura)

No modifiqué nada y no hice commits. La única conexión de red fue un `git ls-remote` de lectura a GitHub; no hubo contacto con Stacker News ni con relays.

### Resumen
Lo técnico está sólido: el código es publicable, reproducible y sin secretos. Los riesgos reales para la evaluación están en **evidencia y documentación**, no en el código. Ninguno impide entregar, pero los dos primeros conviene resolverlos antes.

### Hallazgos por severidad

| # | Sev. | Hallazgo | Evidencia |
|---|---|---|---|
| 1 | **Alta** | Las conversaciones de **ChatGPT** previas a la Fase 0.1 siguen **NO RECUPERADAS**. La prueba exige registros de conversaciones con IA y solo tú puedes aportarlas. Cuatro transcripciones tempranas (`0.1_02`, `_04`, `_05`, `_08`) también llevan marcas de «no recuperada». | `docs/ai-log.md` §«Interacciones no recuperadas» |
| 2 | **Alta** | La evidencia de la autenticación real en Stacker News es **declarativa en el lado de Stacker News**. B4 tiene auditoría sanitizada del firmante: 16 eventos, `sign_ok` 1, 0 errores. De Stacker News solo hay tu observación, sin captura ni prueba de que la sesión persista al recargar. La segunda ejecución (2026-11-22) es un PASS que tú declaraste, sin evidencia técnica. La documentación lo dice con honestidad. | `docs/evidence/b4-*`, `docs/decisions.md` («B4: ejecución real y resultado»), README §2 |
| 3 | Media | El **README no es breve**: 550 líneas y unas 9.100 palabras. El camino del evaluador está arriba, pero no hay una sección corta de **alcance, supuestos y tradeoffs**. Esos contenidos están dispersos en `docs/decisions.md` (D-8, D-9, D-17 y las secciones «Supuestos y límites»). El README sí cubre limitaciones en §13. | README, `decisions.md` |
| 4 | Media | **Trazabilidad 40–54 toda PARCIAL.** Es esperable porque las 15 interacciones pertenecen a la misma sesión, que sigue abierta. Además, las transcripciones excluyen razonamiento interno y salidas de herramientas. | `ai-log.md`, cabeceras de `docs/ai-sessions/` |
| 5 | Baja | **Error de referencia en `ai-log.md`.** La entrada «ChatGPT» (línea ~809) enlaza a la transcripción 31 de B4 y la marca «Completa», lo que no corresponde. | `docs/ai-log.md:809` |
| 6 | Baja | 34 pruebas se omiten en un clon limpio: 8 vectores NIP-44 que no se versionan por licencia, 1 de permisos POSIX y 25 de Docker. Está documentado. | README §9 |
| 7 | Info | El correo de autoría es público en la historia. El firmante de B6.2 sigue activo en tu máquina, con su contraseña en el historial local de la sesión, fuera del repo. Las dependencias siguen sin hashes (D-6). | HANDOFF §8 |

### Resultados reales de las verificaciones
- **Git:** rama `main`, `HEAD` = `origin/main` = `93c4f52…`, 0 cambios pendientes.
- **Clon limpio:** el clon y la validación Docker se ejecutaron sobre `657c876`, no sobre `HEAD`. `HEAD` difiere solo en 5 archivos de documentación y trazabilidad. Esa validación dio 1025 passed, 34 skipped, 0 failed, y 36 comprobaciones Docker sin fallos (login 200/401, persistencia, idempotencia). En esta auditoría **no la repetí**.
- **Enlaces:** los 29 enlaces relativos del README existen. No quedan referencias a `b62`, `d17`, `8001` ni a archivos privados.
- **Transcripciones:** los 59 archivos de `docs/ai-sessions/` están enlazados en el índice y ningún enlace apunta a un archivo inexistente.
- **`python tools/ai_sessions.py check`:** resultado real **«2 pendiente(s)»**.
  - La interacción 54 está desactualizada: la sesión llega hasta 13:07 UTC y la transcripción hasta 13:03.
  - El prompt de esta auditoría aún no está registrado en el manifiesto.
  - Ambos pendientes son consecuencia de la sesión abierta, no una pérdida.

### Matriz de cumplimiento

| Requisito | Estado | Nota |
|---|---|---|
| Repositorio publicado = estado local | **CUMPLE** | `93c4f52`, `main`, sin pendientes |
| Aplicación en Python | **CUMPLE** | Python 3.12 + FastAPI |
| Crear o ingresar clave secreta Nostr | **CUMPLE** | `POST/PUT /identity` y la interfaz; pruebas automatizadas |
| Firmante NIP-46 propio | **CUMPLE** | Regresión con NDK 2.12.2 (automatizada) y las dos validaciones reales |
| Ejecutable desde un clon limpio, sin archivos privados | **CUMPLE** | Verificado en `657c876`; no repetido aquí |
| Ausencia de secretos en lo publicado | **CUMPLE** | Escaneos de patrones; la contraseña de B6.2 no está en el árbol ni en la historia |
| Autenticación real en Stacker News | **PARCIAL** | Hallazgo 2 |
| README breve | **PARCIAL** | Hallazgo 3 |
| Supuestos y tradeoffs | **PARCIAL** | Existen en `decisions.md` y en README §13, sin resumen en el README |
| Decisión de alcance mínimo y extras justificados | **PARCIAL** | Los extras (login con SQLite/Argon2/JWT, modo continuo, laboratorio) están en las decisiones, pero el README no los justifica en breve |
| Registros de conversaciones con IA | **PARCIAL** | Claude Code bien cubierto; ChatGPT no recuperado |
| Transcripciones 40–54 completas | **PARCIAL** | Todas PARCIAL por sesión abierta; el `check` de las 40–53 está al día |
| Persistencia de la sesión de Stacker News al recargar | **NO VERIFICADO** | No se reportó en B4 |
| Detalle técnico de la segunda validación real | **NO VERIFICADO** | PASS declarado por el propietario |
| Interacciones con Codex | **NO VERIFICADO** | Sin constancia; el índice lo señala como laguna posible |

### Acciones mínimas propuestas (ninguna aplicada)
1. **Tú:** exportar las conversaciones de ChatGPT de la Fase 0.1. Si no existen, declarar su pérdida de forma explícita en el README y en `ai-log.md`. Yo las redacto y las incorporo.
2. **README:** agregar una sección de unas 20 líneas, «Alcance, supuestos y tradeoffs». Debe cubrir el mínimo exigido, los extras justificados (login local, modo continuo, laboratorio) y los límites deliberados (sin persistir claves, un solo administrador, sin hashes de dependencias), con enlaces a D-3, D-8, D-9 y D-17. No haría falta recortar el resto del README.
3. **`ai-log.md`:** corregir la línea 809, de modo que la entrada de ChatGPT no cite la transcripción 31.
4. **Al cerrar la sesión:** registrar esta auditoría como interacción 55, reexportar las transcripciones 40–55 y ejecutar `check`. Las «Parciales» solo pasan a «Completa» si la herramienta lo permite una vez cerrada.
5. **Opcional y con nueva autorización de alcance definido:** repetir la autenticación real capturando evidencia (pantalla o vídeo más la auditoría sanitizada), incluida la comprobación de persistencia al recargar. Eso cerraría el hallazgo 2.

Las acciones 2, 3 y 4 requieren un commit local y, después, tu autorización para el push; no hago nada de eso sin tu confirmación.

## Prompt del propietario (2026-11-22T13:10:26.909Z)

Claude, revisé tu informe de auditoría final y autorizo una etapa de cierre documental acotada.

**Objetivo:** corregir los hallazgos documentales sin modificar el funcionamiento del producto.

### Tareas autorizadas

1. Agregar al inicio del README una sección breve de «Alcance, supuestos y tradeoffs», que explique:
   - Qué exige la prueba técnica y cómo se cumple.
   - Por qué se utilizó Python.
   - Qué funcionalidades adicionales se incorporaron y por qué.
   - Qué funcionalidades se dejaron deliberadamente fuera.
   - Qué decisiones de seguridad se adoptaron.
   - Referencias a las decisiones técnicas existentes.

2. Corregir la referencia incorrecta de ChatGPT en `docs/ai-log.md`, sin atribuir a ChatGPT una transcripción de Claude Code.

3. Revisar las interacciones de IA marcadas como no recuperadas. Mantener esa clasificación cuando corresponda; no inventar contenido ni reconstruir conversaciones como si fueran literales.

4. Preparar el procedimiento para cerrar y reexportar las transcripciones pendientes, sin declararlas completas mientras la sesión permanezca abierta.

5. Ejecutar las comprobaciones documentales pertinentes y verificar que los enlaces del README sigan funcionando.

### Restricciones

- No modificar código funcional, pruebas, dependencias ni configuración Docker.
- No modificar el contenedor B6.2, sus credenciales, bases ni volúmenes.
- No realizar conexiones con Stacker News ni relays.
- No ejecutar commit ni push todavía.
- No publicar secretos ni datos sensibles.
- No borrar documentación histórica.

### Entregable

Presentar el diff de los archivos modificados, el resultado de las verificaciones y los pendientes que requieren mi intervención.

Esperar mi autorización antes de crear cualquier commit.

<!-- 2026-11-22T13:10:50.258Z -->
Empiezo leyendo las decisiones que voy a citar, para no afirmar nada que no esté registrado (en especial por qué se eligió Python).

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Edit — README.md]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\97ea8763-694e-4b53-8496-52b85c37bc64\scratchpad\entry55.py]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T13:13:07.141Z -->
Cierre documental listo en el árbol de trabajo, **sin commit ni push**. Se tocaron `README.md`, `docs/ai-log.md`, `tools/ai_sessions_manifest.json` y la transcripción 54. Además hay un archivo nuevo, la transcripción 55. No hay cambios en código, pruebas, dependencias ni Docker. No se tocó B6.2 y no hubo contacto con Stacker News ni con relays.

## Diff (`git diff --stat`, +100/−2)

| Archivo | Cambio |
|---|---|
| `README.md` (+31) | Sección «Alcance, supuestos y tradeoffs» antes de «Instalación oficial» |
| `docs/ai-log.md` (+29/−1) | Línea de ChatGPT corregida, checklist de cierre y entrada 55 |
| `tools/ai_sessions_manifest.json` (+8) | Interacción 55 registrada |
| `docs/ai-sessions/…_54-…md` (+34/−1) | Reexportada, sigue PARCIAL |
| `docs/ai-sessions/…_55-auditoria-cierre-documental.md` (nuevo) | PARCIAL |

**1. Sección del README.** Cubre lo que pediste:
- **Exigencias de la prueba:** una tabla con las exigencias y cómo se cumple cada una.
- **Python:** por qué se usó.
- **Funcionalidades adicionales:** cuáles son y por qué.
- **Fuera de alcance:** qué se dejó fuera a propósito.
- **Seguridad:** las decisiones adoptadas.
- **Supuestos y tradeoffs:** los principales.
- **Referencias:** enlaces a D-1, D-3, D-6 a D-10, D-13, D-17 y D-18, a P-47 y P-48, a `nip46-security-design.md` y a `stacker-news-compatibility.md`.

Dos decisiones que conviene que conozcas:
- La puse como `###` bajo el título, no como `##`. Una prueba existente exige que la primera sección `##` sea la instalación, y no me autorizaste a editar pruebas.
- **No inventé el motivo de elegir Python.** Ningún registro lo recoge. El texto dice que lo fijaste tú como stack (`AGENTS.md` §2, D-6) y que ese motivo no quedó registrado. Lo que sí documenta es que `coincurve` y `cryptography` cubren la criptografía necesaria y se validaron en el laboratorio contra NDK 2.12.2.

**2. Referencia de ChatGPT.** La línea que enlazaba por error a la transcripción 31 de Claude Code ahora dice «no recuperada». Aclara que no existe ningún archivo para esas conversaciones y que se corrigió el 2026-11-22.

**3. Interacciones no recuperadas.** Las revisé y mantengo la clasificación. Corrijo mi auditoría anterior: las marcas «no recuperada» de las transcripciones `0.1_02`, `_04`, `_05` y `_08` **no indican contenido perdido**. Solo hablan de la política o de la laguna de ChatGPT. Lo único no recuperado son las conversaciones de ChatGPT previas a la Fase 0.1, y no hay constancia de Codex. No reconstruí nada.

**4. Procedimiento de cierre.** Añadí a `docs/ai-log.md` el checklist «Cómo cerrar y reexportar una sesión abierta», de 8 pasos:
- Las transcripciones 40 a 55 son de una misma sesión abierta y no se declaran completas hasta cerrarla. No se fuerza con `--now`.
- Una contraseña compartida en el chat se redacta con `--redact-user` sin escribir su valor en ningún archivo.
- Las etiquetas «Parcial» solo pasan a «Completa» donde la herramienta lo marque.

## Verificaciones
| Comprobación | Resultado |
|---|---|
| Enlaces relativos del README | 29, ninguno roto |
| Pruebas de README y de trazabilidad | 70 passed (27 de README, 54 de trazabilidad; 11 se solapan) |
| `python tools/ai_sessions.py check` | «trazabilidad OK» justo tras exportar. Se desactualiza con cada mensaje nuevo, porque la sesión sigue abierta |
| `scan --blocking-only` | 1 aviso: la clave pública de B4 (`c5a035bf…`) en una transcripción antigua ya publicada. Es pública y está revisada; con `--allow-hex-prefix c5a035bf` queda «sin hallazgos» |
| Contraseña de B6.2 en el árbol y en la historia (19 commits) | 0 coincidencias |
| `git diff --check` | limpio |

## Pendiente de tu intervención
1. **Autorizar el commit** de estos cambios y, aparte, el push. Esperaré tu orden.
2. **Revisar la frase sobre Python** en el README y, si recuerdas el motivo real, completarla. Yo no lo reconstruyo.
3. **Aportar las conversaciones de ChatGPT** de la Fase 0.1, o aceptar que queden declaradas como no recuperadas.
4. **Cerrar esta sesión.** Después reexporto las transcripciones 40 a 55, cambio las etiquetas a «Completa» solo donde la herramienta lo permita y vuelvo a ejecutar `check`. Eso requiere un commit posterior y tu autorización.
5. **Opcional, con nueva autorización de alcance definido:** repetir la autenticación real capturando evidencia (pantalla o vídeo más auditoría sanitizada). Eso cerraría el hallazgo principal de la auditoría.

## Prompt del propietario (2026-11-22T13:20:39.267Z)

# Informe de cierre — Revisión de la prueba técnica NIP-46

**Proyecto:** `nostr-nip46-remote-signer`  
**Referencia:** Auditoría final y cierre documental del 22-11-2026.

## 1. Corrección de la justificación de Python

El propietario confirma que eligió Python por los siguientes motivos:

- Era el lenguaje que más conocía entre las alternativas permitidas por la prueba.
- Ya lo había utilizado anteriormente, aunque su experiencia práctica era limitada.
- Estaba familiarizado con su sintaxis basada en indentación.
- Permitía utilizar FastAPI para implementar la solución.

**Acción:** actualizar únicamente la justificación de Python en el README, reflejando estos motivos de forma breve y fiel.

No atribuir la elección a una mayor facilidad de aprendizaje, al uso de agentes de IA ni a otros motivos no declarados.

## 2. Registros de conversaciones con IA

Las conversaciones antiguas de ChatGPT que no estén disponibles deben permanecer identificadas como **«no recuperadas»**.

No inventar, reconstruir ni presentar resúmenes como transcripciones originales.

Mantener la trazabilidad existente de Claude Code y las referencias a las interacciones efectivamente recuperadas.

## 3. Cierre documental

Conservar los cambios ya preparados:

- Sección «Alcance, supuestos y tradeoffs» del README.
- Corrección de la referencia incorrecta de ChatGPT en `docs/ai-log.md`.
- Registro de la interacción 55.
- Procedimiento de cierre y reexportación de transcripciones.

Las transcripciones de sesiones abiertas deben continuar identificadas como **PARCIAL** hasta que puedan verificarse como completas.

## 4. Restricciones

- No modificar código funcional, pruebas, dependencias ni Docker.
- No intervenir B6.2, sus credenciales, bases o volúmenes.
- No realizar conexiones externas con Stacker News ni relays.
- No incorporar nuevas funcionalidades.
- No realizar commit ni push sin autorización expresa.
- No introducir secretos en archivos ni registros.

## 5. Resultado esperado

Aplicar únicamente la corrección de la justificación de Python y verificar que los cambios documentales pendientes sean coherentes.

Entregar un resumen del diff, resultados de las verificaciones y estado de la trazabilidad.

**No ejecutar commit ni push. Esperar autorización del propietario.**

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T13:21:10.494Z -->
La justificación de Python quedó actualizada con tus cuatro motivos. No hay commit ni push, y sigo esperando tu autorización.

## Qué cambió en esta pasada
**Justificación de Python (`README.md`).** Quedó así:

> Motivos declarados por el propietario: entre los lenguajes que permitía la prueba (Python, Rust, Elixir y Go) era el que **más conocía**; ya lo había usado antes, aunque con **experiencia práctica limitada**; le resultaba familiar su sintaxis basada en indentación, y permitía usar **FastAPI**. Quedó fijado como stack en `AGENTS.md` §2 y D-6.

- **No atribuí** la elección a facilidad de aprendizaje, a agentes de IA ni a otros motivos no declarados.
- **Dato técnico aparte:** conservé una frase separada sobre `coincurve` y `cryptography`, rotulada como «dato técnico verificado, que no es el motivo de la elección». Si prefieres que no figure junto a los motivos, la quito.
- **Coherencia:** eliminé de README e índice la frase que decía que el motivo no constaba en ningún registro. La entrada 55 de `docs/ai-log.md` ahora dice que la justificación recoge solo lo que declaraste y que son tres prompts, no dos.

## Lo que se mantuvo
- La sección «Alcance, supuestos y tradeoffs», la corrección de ChatGPT, la entrada 55 y el checklist de cierre.
- Las conversaciones antiguas de ChatGPT siguen como «no recuperadas».
- La trazabilidad de Claude Code no se tocó. La transcripción 55 se reexportó con tus mensajes de hoy y sigue **PARCIAL**, igual que la 54 y las 40 a 53, porque la sesión sigue abierta.

## Diff y estado
Los archivos modificados son `README.md`, `docs/ai-log.md`, `tools/ai_sessions_manifest.json` y la transcripción 54. La transcripción 55 es nueva. En conjunto son +100/−2 líneas. No se tocó código, pruebas, dependencias, Docker ni B6.2, y no hubo conexiones externas.

## Verificaciones
- **`check`:** «trazabilidad OK» justo tras exportar; vuelve a desactualizarse con cada mensaje porque la sesión sigue abierta.
- **Pruebas:** 70 passed (trazabilidad y README).
- **Enlaces del README:** 29, ninguno roto.
- **Escaneo de secretos:** sin hallazgos, con la clave pública de B4 ya revisada como excepción.
- **Contraseña de B6.2:** 0 coincidencias en el árbol y en la historia.
- **Diff:** `git diff --check` limpio.

## Pendiente de ti
1. Autorizar el commit y, por separado, el push.
2. Cerrar la sesión para reexportar las transcripciones 40 a 55 y pasarlas a «Completa» solo donde la herramienta lo permita. Esto requiere otro commit con tu autorización.
3. Aportar las conversaciones de ChatGPT de la Fase 0.1, o aceptar que queden como no recuperadas.
