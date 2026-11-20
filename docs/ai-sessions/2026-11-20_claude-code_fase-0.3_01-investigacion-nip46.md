# Investigación y diseño de interoperabilidad NIP-46 con Stacker News (Fase 0.3)

| Campo | Valor |
|---|---|
| Fecha del prompt (UTC) | 2026-11-20T16:59:07.134Z |
| Fase | 0.3 |
| Agente | Claude Code (extensión de VS Code, versión 2.1.329) |
| Modelo | claude-sonnet-5-5 (campo `model` de los registros de sesión) |
| Nivel de razonamiento | high (campo `effort` de los registros de sesión) |
| Sesión | 35f0f3c1-13e9-47b9-832f-f6252cd2166f |
| Origen de la transcripción | Archivo de sesión local de Claude Code (JSONL), extraído con script; no reconstruido |
| Estado | Completa (contenido visible) |

**Qué contiene y qué no.** Prompt del propietario (sin las etiquetas `<pasted_content>` que añade el cliente) y todo el texto visible de las respuestas de Claude Code, en orden. Las llamadas a herramientas se indican con una línea de marcador; su contenido y sus salidas no se incluyen, porque los archivos resultantes están en el repositorio. **No se incluye razonamiento interno del modelo** ni contexto del sistema. Redacción aplicada: usuario local, nombre del autor y correos; la ruta absoluta del proyecto se acortó a ruta relativa. Las marcas `<!-- fecha -->` son del archivo de sesión.

---

## Prompt del propietario (2026-11-20T16:59:07.134Z)

# FASE 0.3 — Investigación y diseño de interoperabilidad NIP-46 con Stacker News

Actúa como arquitecto de software senior especializado en Python, Nostr, NIP-46, criptografía aplicada, protocolos WebSocket y seguridad.

Estamos desarrollando `nostr-nip46-remote-signer`, una aplicación Python cuyo objetivo final es implementar un firmante remoto Nostr y demostrar una autenticación real con Stacker News.

La Fase 0.2 fue completada, aprobada y publicada en GitHub mediante el commit:

`392448b3f918bed466824db495008cbd35675898`

**Autorizo iniciar exclusivamente la Fase 0.3, enfocada en investigación, análisis de compatibilidad y diseño técnico.**

No autorizo todavía la implementación funcional del firmante.

## 1. Contexto obligatorio

Antes de trabajar, revisa:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/project-context.md`
- `docs/decisions.md`
- `docs/ai-log.md`
- `README.md`
- `pyproject.toml`
- La implementación actual de FastAPI.
- El estado del repositorio Git.

Confirma que la rama local está sincronizada con `origin/main`.

No modifiques archivos de código, dependencias ni configuraciones de infraestructura durante esta fase.

## 2. Objetivo principal

Determinar los requisitos técnicos necesarios para que nuestra aplicación Python pueda funcionar como firmante remoto NIP-46 y autenticar una cuenta Nostr en Stacker News.

Debemos identificar:

1. El flujo de conexión compatible con Stacker News.
2. Los métodos NIP-46 necesarios.
3. El cifrado requerido.
4. El formato de los mensajes y eventos.
5. Los requisitos de conexión a relays.
6. Las operaciones de autorización y firma.
7. Los requisitos mínimos para una demostración real.
8. Las decisiones de arquitectura necesarias para implementar el firmante.

No debemos asumir que cumplir genéricamente NIP-46 garantiza compatibilidad con Stacker News.

## 3. Fuentes de investigación

Prioriza fuentes oficiales y código fuente vigente.

### A. Especificación NIP-46

https://github.com/nostr-protocol/nips/blob/master/46.md

Analiza la versión actual del documento y registra la fecha de consulta y, cuando sea posible, el commit o revisión examinada.

Investiga también las especificaciones relacionadas:

- NIP-01: eventos y comunicación con relays.
- NIP-44: cifrado de mensajes.
- NIP-04: compatibilidad heredada, si corresponde.
- NIP-19: representación de claves e identificadores.
- NIP-46: conexión y firma remota.

No incorpores protocolos adicionales sin justificar su necesidad.

### B. Stacker News

Investiga la implementación actual de Stacker News.

Repositorio de referencia:

https://github.com/stackernews/stacker.news

Busca específicamente:

- Inicio de sesión mediante Nostr.
- Soporte NIP-46.
- Conexiones `bunker://`.
- Conexiones `nostrconnect://`.
- Integraciones con firmantes remotos.
- Métodos de firma utilizados durante la autenticación.
- Validación de claves públicas y firmas.
- Requisitos adicionales para completar una sesión.

Identifica archivos, funciones y referencias concretas del código fuente.

No afirmes compatibilidad sin evidencia.

### C. Implementaciones de referencia

Investiga implementaciones conocidas como nsec.app y nsecBunker.

Utilízalas para comprender el comportamiento esperado y detectar diferencias de interoperabilidad.

Distingue siempre entre:

- Requisitos normativos.
- Comportamientos específicos de Stacker News.
- Convenciones de otras implementaciones.
- Hipótesis pendientes de comprobar.

## 4. Flujos de conexión

Analiza por separado:

### Flujo A — bunker://

El firmante remoto genera una URI que el usuario proporciona al cliente.

Investiga:

- Estructura de la URI.
- Clave pública del firmante remoto.
- Parámetros relay.
- Secretos opcionales.
- Solicitud `connect`.
- Autorización de clientes.
- Recuperación de la clave pública real del usuario.

### Flujo B — nostrconnect://

El cliente genera una URI que el firmante debe procesar.

Investiga:

- Clave pública del cliente.
- Relays indicados.
- Secret de conexión.
- Permisos solicitados.
- Respuesta de conexión.
- Validación del secreto.
- Protección contra suplantación.

Determina cuál de los dos flujos debemos priorizar para la prueba con Stacker News.

Si Stacker News soporta ambos, documenta las diferencias y recomienda el camino de menor complejidad para una primera autenticación real.

## 5. Contrato NIP-46

Documenta los mensajes necesarios para:

- `connect`
- `ping`
- `get_public_key`
- `sign_event`
- `nip04_encrypt`
- `nip04_decrypt`
- `nip44_encrypt`
- `nip44_decrypt`
- `logout`
- `switch_relays`

No todos tienen que implementarse inicialmente.

Clasifícalos en:

- Obligatorios para la interoperabilidad.
- Necesarios específicamente para Stacker News.
- Opcionales.
- No requeridos para la primera demostración.

Para cada método relevante, documenta:

- Parámetros.
- Respuesta esperada.
- Errores posibles.
- Permisos necesarios.
- Consideraciones de seguridad.

Presta especial atención a la distinción entre la clave pública de transporte del firmante remoto y la clave pública de identidad del usuario.

## 6. Eventos y criptografía

Investiga:

- Estructura de eventos Nostr `kind 24133`.
- Etiquetas `p`.
- Cifrado de solicitudes y respuestas.
- Derivación de claves y establecimiento de conversaciones.
- Generación de identificadores de eventos.
- Firmas Schnorr.
- Verificación de firmas.
- Correlación entre solicitudes y respuestas.
- Validación de remitentes.
- Protección frente a respuestas duplicadas o solicitudes repetidas.
- Caducidad de solicitudes y sesiones.

Confirma el uso de NIP-44 según la especificación vigente y determina si Stacker News exige algún mecanismo de compatibilidad adicional.

No diseñes criptografía propia si existen bibliotecas confiables y compatibles.

## 7. Relays Nostr

Investiga cómo se intercambian los eventos entre cliente y firmante.

Documenta:

- Conexiones WebSocket.
- Suscripciones y filtros.
- Publicación de eventos.
- Confirmaciones y errores.
- Reconexión.
- Timeouts.
- Duplicados.
- Manejo de interrupciones.
- Uso de uno o varios relays.

Propón una estrategia mínima para la primera prueba real.

No conectes todavía a relays públicos ni publiques eventos.

## 8. Seguridad

Diseña un modelo mínimo que contemple:

- Generación de claves de prueba.
- Separación entre claves de identidad y transporte.
- Protección de claves privadas.
- Autorización explícita de clientes.
- Permisos por operación.
- Confirmación antes de firmar eventos sensibles.
- Prevención de filtración de secretos.
- Registro seguro de errores.
- Revocación de sesiones.
- Prevención de ataques de repetición.

No utilices claves personales reales durante la investigación.

No almacenes secretos en el repositorio, documentación o registros.

## 9. Evaluación de bibliotecas Python

Investiga bibliotecas disponibles para:

- Nostr.
- WebSockets.
- NIP-44.
- Schnorr/secp256k1.
- Validación de eventos.

Para cada alternativa relevante, compara:

- Compatibilidad con Python 3.12.
- Soporte de NIP-46.
- Mantenimiento.
- Dependencias.
- Licencia.
- Riesgos de seguridad.
- Facilidad de integración.
- Compatibilidad con nuestra arquitectura.

Entrega una recomendación técnica fundamentada.

No instales dependencias todavía.

## 10. Diseño de arquitectura

Propón los componentes mínimos que necesitará nuestra aplicación.

Considera:

- Gestión de claves.
- Cliente de relays.
- Transporte de mensajes NIP-46.
- Cifrado y descifrado.
- Procesamiento de solicitudes.
- Autorización.
- Firma de eventos.
- Gestión de conexiones.
- API FastAPI.
- Persistencia futura.

Mantén separadas las responsabilidades.

Evita introducir abstracciones innecesarias o una arquitectura excesivamente compleja.

Define las interfaces principales y sus responsabilidades, sin implementar todavía el código.

## 11. Plan de prueba real con Stacker News

Diseña un procedimiento reproducible para demostrar que nuestro firmante funciona.

Debe contemplar:

1. Crear una identidad Nostr exclusiva para pruebas.
2. Ejecutar el firmante Python.
3. Establecer conexión con los relays necesarios.
4. Iniciar el flujo de autenticación desde Stacker News.
5. Autorizar la conexión.
6. Procesar las solicitudes NIP-46.
7. Firmar los eventos requeridos.
8. Completar la autenticación.
9. Verificar que Stacker News reconoce la identidad.
10. Registrar evidencia técnica sin exponer secretos.

Define qué evidencia demostraría que el login fue realmente exitoso y qué resultados solo demostrarían conectividad parcial.

Identifica dependencias externas, riesgos y pasos que requieran intervención humana.

No realices todavía la autenticación real.

## 12. Documentación requerida

Crea documentos técnicos en `docs/`, utilizando nombres descriptivos y coherentes con la estructura existente.

Como referencia:

- `docs/nip46-protocol-analysis.md`
- `docs/stacker-news-compatibility.md`
- `docs/nip46-security-design.md`
- `docs/nip46-implementation-plan.md`

Puedes consolidarlos si resulta más claro.

Cada documento debe distinguir:

- Hechos verificados.
- Referencias y enlaces a fuentes.
- Inferencias técnicas.
- Riesgos.
- Decisiones propuestas.
- Preguntas pendientes.

Incluye diagramas de secuencia en Mermaid cuando aporten claridad.

Actualiza `docs/decisions.md` únicamente para registrar decisiones propuestas o pendientes. No declares como aprobadas decisiones que el propietario todavía no haya autorizado.

Registra la participación de IA conforme a `AGENTS.md` §9.

## 13. Criterios de aceptación

La fase se considerará lista para revisión cuando:

- Se haya examinado la especificación NIP-46 vigente.
- Se haya investigado el código de Stacker News.
- Se haya determinado el flujo de conexión prioritario.
- Se hayan identificado los métodos necesarios para el login.
- Se haya definido la estrategia de cifrado.
- Se haya propuesto una arquitectura mínima.
- Se hayan evaluado bibliotecas Python.
- Exista un procedimiento verificable de prueba real.
- Los riesgos y las incertidumbres estén documentados.

Si no puedes verificar algún requisito, indícalo explícitamente y describe cómo comprobarlo.

No inventes resultados ni afirmes que el login funciona.

## 14. Restricciones

- No implementar el firmante.
- No modificar código funcional.
- No instalar dependencias.
- No conectar con relays públicos.
- No realizar autenticación real.
- No crear ni almacenar claves privadas.
- No modificar `AGENTS.md` ni `CLAUDE.md`.
- No ejecutar commits.
- No ejecutar push.
- No avanzar a la Fase 1.0.
- No modificar ramas ni remotos.

## 15. Informe final

Entrega:

1. Resumen ejecutivo de los hallazgos.
2. Fuentes y versiones examinadas.
3. Flujo de autenticación recomendado.
4. Métodos NIP-46 necesarios.
5. Requisitos criptográficos.
6. Bibliotecas Python recomendadas.
7. Arquitectura propuesta.
8. Plan de implementación por tareas.
9. Procedimiento de prueba real con Stacker News.
10. Riesgos y decisiones pendientes.
11. Archivos creados o modificados.
12. Estado de Git.

Detente y espera revisión y aprobación humana antes de implementar o confirmar cambios.


## Respuesta de Claude Code

<!-- 2026-11-20T16:59:15.669Z -->
Empiezo verificando el estado de Git (incluida la sincronización con el remoto, sin alterar referencias locales) y el entorno de investigación.

> *[Llamada a herramienta: PowerShell — Check git sync with remote and tool availability]*

> *[Llamada a herramienta: ToolSearch]*

<!-- 2026-11-20T16:59:23.281Z -->
Git sincronizado con `origin/main` (ambos en `392448b`). Descargo las especificaciones oficiales a un directorio nuevo del scratchpad, junto con el commit examinado (solo lectura, sin credenciales).

> *[Llamada a herramienta: PowerShell — Download official NIP specs and commit metadata]*

<!-- 2026-11-20T16:59:39.104Z -->
Dato relevante: `master` está en `bec0fc89…` (2026-11-16) y `46.md` cambió hace poco (logout, metadatos de cliente, timeouts), así que debo leer la versión vigente completa.

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-nips/46.md]*

<!-- 2026-11-20T16:59:44.793Z -->
NIP-46 vigente leída. Leo ahora NIP-44 (cifrado), cuyo texto también cambió en junio de 2026.

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-nips/44.md]*

> *[Llamada a herramienta: PowerShell — Shallow clone Stacker News repo for read-only analysis]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

<!-- 2026-11-20T17:00:10.813Z -->
Stacker News usa `NDKNip46Signer` de NDK con un parche propio. Leo los dos archivos clave completos.

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-sn/lib/nostr.js]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-sn/components/nostr-auth.js]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-sn/pages/api/auth/[...nextauth].js]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: PowerShell — Download NDK 2.12.2 package and verify integrity]*

<!-- 2026-11-20T17:00:49.105Z -->
Integridad verificada (el hash coincide con el lockfile). El paquete incluye `src/`; localizo la implementación NIP-46.

> *[Llamada a herramienta: Glob]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-ndk/x/package/src/signers/nip46/index.ts]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-ndk/x/package/src/signers/nip46/rpc.ts]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-ndk/x/package/src/events/index.ts]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-ndk/x/package/src/events/index.ts]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-ndk/x/package/src/signers/nip46/backend/index.ts]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-ndk/x/package/src/signers/nip46/backend/connect.ts]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-ndk/x/package/src/signers/nip46/backend/sign-event.ts]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-ndk/x/package/src/events/index.ts]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-nips/01.md]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-nips/01.md]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-nips/04.md]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-nips/42.md]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-nips/19.md]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-nips/98.md]*

> *[Llamada a herramienta: PowerShell — Collect PyPI metadata for candidate Python libraries]*

> *[Llamada a herramienta: PowerShell — Print remaining PyPI candidate summaries]*

> *[Llamada a herramienta: Edit — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/pypi_summary.py]*

> *[Llamada a herramienta: PowerShell — Summarize remaining PyPI candidates]*

<!-- 2026-11-20T17:03:05.080Z -->
Ahora el estado en GitHub de las bibliotecas y de las implementaciones de referencia (nsec.app/noauth, nsecBunkerd), y búsqueda del soporte NIP-46 de rust-nostr (`nostr-sdk`).

> *[Llamada a herramienta: PowerShell — Collect GitHub repo metadata for libraries and references]*

> *[Llamada a herramienta: PowerShell — List NIP-46 related files in rust-nostr repository tree]*

> *[Llamada a herramienta: PowerShell — Inspect rust-nostr tree layout]*

> *[Llamada a herramienta: PowerShell — Inspect nostr-sdk PyPI metadata and wheels]*

> *[Llamada a herramienta: PowerShell — Look for NIP-46 support in nostr-sdk-ffi bindings]*

> *[Llamada a herramienta: PowerShell — Inspect nostr-sdk-ffi NIP-46 API surface]*

> *[Llamada a herramienta: PowerShell — Fetch reference implementation READMEs and trees]*

> *[Llamada a herramienta: PowerShell — List noauth source modules and nsecbunkerd tree]*

> *[Llamada a herramienta: PowerShell — Read nsecbunkerd README and noauth file list]*

> *[Llamada a herramienta: PowerShell — Fetch nsec.app NIP-46 backend source and grep key behaviors]*

<!-- 2026-11-20T17:04:45.972Z -->
Error de comillas en mi patrón; lo repito con la herramienta Grep.

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-ref/noauth-nip46.ts]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-ref/noauth-nip46.ts]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: PowerShell — Check coincurve Schnorr API and NIP-44 test vector checksum]*

> *[Llamada a herramienta: PowerShell — Check nsec.app default relays and SN FAQ mentions]*

<!-- 2026-11-20T17:06:27.039Z -->
Casi listo para redactar. Dos comprobaciones finales: ruedas (wheels) de `coincurve` para Python 3.12 en Windows/Linux, y huellas SHA-256 de las fuentes examinadas para la trazabilidad.

> *[Llamada a herramienta: PowerShell — Check wheel availability and hash examined sources]*

> *[Llamada a herramienta: PowerShell — List cryptography wheels for Windows and Linux x86_64]*

<!-- 2026-11-20T17:07:46.810Z -->
Antes de redactar, dos comprobaciones más sobre bibliotecas: si existen implementaciones NIP-44 en Python (repo de referencia de paulmillr y `pynostr`).

> *[Llamada a herramienta: PowerShell — Check for Python NIP-44/NIP-46 support in candidate repos]*

<!-- 2026-11-20T17:07:57.462Z -->
Investigación completada. Redacto los documentos técnicos. Primero el análisis del protocolo.

> *[Llamada a herramienta: Write — docs/nip46-protocol-analysis.md]*

<!-- 2026-11-20T17:09:10.273Z -->
Corrijo un detalle: en NIP-01 el ejemplo `mute:` es un `OK` con `false`, no `true`.

> *[Llamada a herramienta: Edit — docs/nip46-protocol-analysis.md]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Read — C:/Users/[REDACTADO:usuario-local]/AppData/Local/Temp/claude/b79ef0bdbf584b14/35f0f3c1-13e9-47b9-832f-f6252cd2166f/scratchpad/src-sn/proxy.js]*

<!-- 2026-11-20T17:09:38.274Z -->
Confirmado: en producción la CSP solo permite `wss:`/`https:` (`proxy.js:230`), así que un relay local `ws://` queda descartado. Redacto ahora el documento de compatibilidad con Stacker News.

> *[Llamada a herramienta: Write — docs/stacker-news-compatibility.md]*

<!-- 2026-11-20T17:10:41.632Z -->
Corrijo la referencia a pasos del diagrama (la numeración que escribí no coincide con el `autonumber`).

> *[Llamada a herramienta: Edit — docs/stacker-news-compatibility.md]*

<!-- 2026-11-20T17:10:46.650Z -->
Ahora el modelo de seguridad.

> *[Llamada a herramienta: Write — docs/nip46-security-design.md]*

> *[Llamada a herramienta: Edit — docs/nip46-security-design.md]*

<!-- 2026-11-20T17:12:07.451Z -->
Ahora el plan de implementación, con evaluación de bibliotecas, arquitectura y procedimiento de prueba real.

> *[Llamada a herramienta: Write — docs/nip46-implementation-plan.md]*

<!-- 2026-11-20T17:13:23.519Z -->
Dos ajustes de precisión: no verifiqué que `cryptography` «publique avisos de seguridad», y `aiohttp` tiene 9 dependencias contando las condicionales.

> *[Llamada a herramienta: Edit — docs/nip46-implementation-plan.md]*

> *[Llamada a herramienta: Edit — docs/nip46-implementation-plan.md]*

<!-- 2026-11-20T17:13:32.639Z -->
Registro las decisiones propuestas (todas pendientes) en `docs/decisions.md`.

> *[Llamada a herramienta: Edit — docs/decisions.md]*

<!-- 2026-11-20T17:13:55.043Z -->
Registro la participación de IA y las fuentes externas realmente consultadas (`AGENTS.md` §9 y §11), y enlazo los documentos desde el README.

> *[Llamada a herramienta: Edit — docs/ai-log.md]*

> *[Llamada a herramienta: Edit — README.md]*

<!-- 2026-11-20T17:14:21.096Z -->
Antes de cerrar reviso la robustez de los diagramas Mermaid: caracteres como `<`, `#` y `;` dentro de mensajes pueden romper el renderizado.

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Edit — docs/nip46-protocol-analysis.md]*

> *[Llamada a herramienta: Edit — docs/nip46-protocol-analysis.md]*

> *[Llamada a herramienta: Edit — docs/nip46-protocol-analysis.md]*

> *[Llamada a herramienta: Edit — docs/nip46-protocol-analysis.md]*

> *[Llamada a herramienta: Edit — docs/nip46-protocol-analysis.md]*

> *[Llamada a herramienta: Edit — docs/stacker-news-compatibility.md]*

> *[Llamada a herramienta: Edit — docs/stacker-news-compatibility.md]*

> *[Llamada a herramienta: Edit — docs/stacker-news-compatibility.md]*

> *[Llamada a herramienta: Edit — docs/stacker-news-compatibility.md]*

> *[Llamada a herramienta: Edit — docs/stacker-news-compatibility.md]*

<!-- 2026-11-20T17:14:44.727Z -->
Verificaciones finales: estado de Git, formato, ausencia de secretos y de cambios fuera de `docs/` y `README.md`.

> *[Llamada a herramienta: PowerShell — Run final git and formatting checks for Phase 0.3]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

<!-- 2026-11-20T17:14:57.469Z -->
Los 8 hallazgos de 64 hex son los SHA-256 de archivos (7 especificaciones y el `.tgz` de NDK), no claves. Repito el bloque de PowerShell, que falló por un error de sintaxis mío.

> *[Llamada a herramienta: PowerShell — Run final git and formatting checks for Phase 0.3]*

<!-- 2026-11-20T17:15:21.973Z -->
La Fase 0.3 está lista para revisión. Es solo investigación y diseño: no toqué código, dependencias ni infraestructura, y no hice commits ni push. Tampoco me conecté a relays, ni consulté el sitio de Stacker News, ni creé claves, ni ejecuté código de terceros. No hubo validación real con Stacker News.

## 1. Resumen ejecutivo
- **Flujo:** Stacker News solo ofrece `bunker://` (o una dirección NIP-05). No hay `nostrconnect://` en todo su código.
- **Cifrado:** el cliente real (NDK 2.12.2, fijado por el lockfile de Stacker News) arranca con NIP-04, aunque NIP-46 vigente exige NIP-44. Un firmante solo NIP-44 no podría descifrar ni el primer `connect`.
- **Métodos:** el cliente usa solo `connect`, `get_public_key` y `sign_event`. No usa `ping`, `switch_relays` ni `logout`.
- **Evento de login:** firma un `kind 27235` con `["challenge", k1]` como primera etiqueta. El servidor valida el `id`, la firma Schnorr y esa etiqueta.
- **Dónde corre el cliente:** en el navegador del usuario. La CSP de producción solo permite `wss:`, así que un relay local `ws://` no sirve para la prueba real.

## 2. Fuentes y versiones
- **NIP-01, 04, 19, 42, 44, 46 y 98:** `master` @ `bec0fc89` (2026-11-16), con SHA-256 registrados. `46.md` cambió hace poco (`logout`, metadatos, `switch_relays`).
- **Vectores NIP-44:** el checksum coincide con el de la especificación.
- **Stacker News:** commit `0a798c72` (2026-11-12), leído sin ejecutarlo.
- **NDK:** versión 2.12.2, verificada contra el `integrity` del lockfile.
- **nsec.app:** commit `4d3f9a12`. `nsecbunkerd` ya no tiene código en su rama principal, aunque Stacker News aún lo lista.

## 3. Flujo recomendado
`bunker://`. Los detalles y el diagrama están en [stacker-news-compatibility.md](docs/stacker-news-compatibility.md).

## 4. Métodos necesarios
- **Obligatorios para el login:** `connect`, `get_public_key`, `sign_event`.
- **Detalles que no están en la especificación:** `connect` llega con `params[0]` vacío, no con la clave del firmante. Hay que responder exactamente `"ack"`. El `sign_event` no debe alterar ningún campo, porque NDK solo toma la firma.
- **Opcionales o no requeridos:** `ping`, `switch_relays`, `logout` y los métodos de cifrado.

## 5. Criptografía
- **NIP-44 v2:** cifrado principal. Se valida con los vectores oficiales.
- **NIP-04:** aceptarlo solo como entrada, de forma acotada y registrada.
- **Respuestas:** en NIP-44, como hace nsec.app. NDK debería adaptarse según su código, pero es una hipótesis que aún no se ha comprobado en ejecución.
- **Serialización NIP-01:** Python y JavaScript escapan distinto los caracteres de control del `content`, y el `id` depende de ello. Hace falta un serializador propio con pruebas.

## 6. Bibliotecas Python recomendadas
- **`coincurve`:** Schnorr BIP-340 y ECDH.
- **`cryptography`:** ChaCha20, HKDF y AES.
- **`websockets`:** cliente de relays.
- **NIP-44:** implementación propia en `app/nostr/` sobre esas primitivas.
- **Descartadas:** `nostr-sdk` (solo expone el rol cliente de NIP-46), `pynostr` y `python-nostr`. No existe una biblioteca Python que implemente el rol de firmante.

Ninguna está instalada. Son dependencias nuevas y requieren tu aprobación.

## 7. Arquitectura
Componentes, interfaces y regla de dependencias están en [nip46-implementation-plan.md](docs/nip46-implementation-plan.md) §3. El código de protocolo no importa FastAPI. La decisión `config/` frente a `core/` sigue pendiente.

## 8. Plan por tareas
Tareas T0 a T13, con criterio de aceptación y pruebas para cada una (plan §5). Incluyo un laboratorio opcional con NDK 2.12.2 real contra un relay local para resolver la hipótesis de NIP-44 antes de tocar Stacker News. Requeriría aprobar herramientas de desarrollo.

## 9. Prueba real
Plan §6: plantilla de autorización según `AGENTS.md` §11, diez pasos (el 5, el 6 y el 8 son humanos) y una tabla de evidencia. Conectar al relay, recibir `connect`, publicar `ack`, responder `get_public_key` o firmar correctamente son **solo evidencia parcial**. El login completo exige ver la sesión iniciada en Stacker News y que la cuenta corresponda a la identidad de prueba.

## 10. Riesgos y decisiones pendientes
- **Alta:**
  - NIP-04 es inevitable con el cliente actual.
  - La hipótesis de que NDK adopte NIP-44 tras nuestra respuesta no está comprobada.
  - Un `kind 27235` firmado sin restricciones sirve como token HTTP ante otros servicios.
  - Hay que fijar el esquema de cifrado de claves en reposo.
- **Media:**
  - Producción de Stacker News podría diferir de `master`.
  - Ningún relay está verificado.
  - Faltan los hashes de las dependencias.
- **Preguntas:** Q1 a Q9 en el plan §7 y cinco más en el diseño de seguridad. Las decisiones P-01 a P-12 están en `docs/decisions.md`, todas como **propuestas pendientes**.

## 11. Archivos
- **Nuevos:**
  - [nip46-protocol-analysis.md](docs/nip46-protocol-analysis.md)
  - [stacker-news-compatibility.md](docs/stacker-news-compatibility.md)
  - [nip46-security-design.md](docs/nip46-security-design.md)
  - [nip46-implementation-plan.md](docs/nip46-implementation-plan.md)
- **Modificados:** `README.md` (enlaces), `docs/decisions.md` (solo propuestas) y `docs/ai-log.md` (entrada 12, fuentes consultadas y la interacción administrativa del commit).

## 12. Estado de Git
- **Sincronización:** `main` está en `392448b`, igual que `origin/main`.
- **Cambios:** 3 archivos modificados y 4 nuevos, todos en `docs/` o `README.md`.
- **Comprobaciones:** `git diff --check` limpio, nada en staging, sin espacios finales ni CRLF en los archivos nuevos. El pytest sigue en 5 pasadas y no hay `.env` real. Un escaneo de secretos no encontró claves; las únicas cadenas de 64 caracteres hex son SHA-256 de archivos.

## Pendientes de trazabilidad
- **Transcripción de esta interacción:** pendiente, se consolida al cierre de fase.
- **Otros pendientes:** la del commit de la Fase 0.2, las interacciones 06 a 08 de la Fase 0.1 y las conversaciones de ChatGPT.
- **`docs/project-context.md`:** no lo modifiqué, pero su §6 sigue diciendo «Fase 0.2: No iniciada».

Quedo a la espera de tu revisión antes de implementar o confirmar cambios.
