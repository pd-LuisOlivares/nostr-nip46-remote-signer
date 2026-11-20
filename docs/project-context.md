# Contexto del proyecto

> **Origen y naturaleza de este documento.** Es una **síntesis** de discusiones mantenidas por el propietario del proyecto con ChatGPT, proporcionada y revisada por el propietario. **No es una transcripción literal** ni debe leerse como tal. Las decisiones que contiene fueron **establecidas o aprobadas por el propietario**; ChatGPT se utilizó como herramienta complementaria de análisis y no se le atribuyen decisiones. Las transcripciones originales de ChatGPT siguen pendientes de aportarse (ver §7).
>
> **Actualización (2026-11-20, revisión de cierre de la Fase 0.3, por petición del propietario).** Se actualizaron los apartados 2, 3 y 6 para reflejar el estado de las Fases 0.1, 0.2 y 0.3. Las demás secciones conservan el texto de la síntesis original.

## 1. Objetivo del proyecto

Implementar en Python un firmante remoto (*remote signer*) Nostr conforme a **NIP-46** y demostrar una **autenticación real con Stacker News**.

Contexto: prueba técnica para la Secretaría de Gobierno Digital del Ministerio de Hacienda de Chile.

## 2. Stack seleccionado

- Python 3.12.
- FastAPI para API y backend.
- HTML, CSS y JavaScript para la interfaz.
- SQLite para persistencia.
- Docker Compose para ejecución reproducible.
- pytest para pruebas automatizadas.

**Estado de la implementación (actualizado).** Desde la Fase 0.2 el repositorio contiene una base de aplicación mínima: FastAPI con `GET /health`, pruebas con pytest, Docker y Docker Compose. **No existe todavía ninguna funcionalidad Nostr, de firma, de JWT, de SQLite ni de interfaz web**; el resto del stack sigue previsto, no implementado.

## 3. Decisiones de dirección del proyecto

Establecidas o aprobadas por el propietario:

- Organizar el desarrollo en **fases incrementales**.
- Reservar la **Fase 0.1** para configurar `AGENTS.md` y `CLAUDE.md`.
- Reservar la **Fase 0.2** para inicializar la aplicación y Docker.
- Dedicar la **Fase 0.3** a la investigación y el diseño de la interoperabilidad NIP-46 con Stacker News, **sin implementar** el firmante (autorizada por el propietario el 2026-11-20).
- Utilizar **Claude Code** como agente principal de implementación.
- Utilizar **Codex** como herramienta complementaria cuando se requiera.
- Revisar y aprobar los cambios importantes antes de implementarlos.
- No permitir commits ni pushes automáticos.
- Priorizar el funcionamiento real con Stacker News.
- Mantener trazabilidad de las interacciones relevantes con IA (ver `docs/ai-log.md`).

## 4. Consideraciones técnicas discutidas

- JWT corresponde a la autenticación de la API local y **no reemplaza NIP-46**.
- La lógica NIP-46 debe permanecer independiente de FastAPI.
- Las claves privadas Nostr requieren protección y no deben exponerse en logs.
- La compatibilidad real con Stacker News debe **verificarse, no suponerse**.
- El alcance complementario no debe comprometer el objetivo principal.

## 5. Riesgos identificados

- Diferencias entre los mecanismos de conexión que admite Stacker News.
- Compatibilidad de cifrado y mensajes NIP-46.
- Conexión y disponibilidad de relays.
- Protección de claves privadas.
- Autorización de solicitudes de firma.
- Exceso de funcionalidades frente al tiempo disponible.

## 6. Estado actual

Según lo informado por el propietario (2026-11-20), salvo donde se indica lo contrario:

| Elemento | Estado | Verificación |
|---|---|---|
| Git y GitHub configurados | Configurados y sincronizados | Verificado por el agente (2026-11-20): `main` coincide con `origin/main` en `392448b3f918bed466824db495008cbd35675898`, publicado por el propietario. |
| Docker Desktop y WSL 2 | Operativos | Verificado por el agente en la Fase 0.2: Docker 25.0.2 y Compose v2.24.3; imagen construida, contenedor `healthy` y `/health` con HTTP 200. |
| `AGENTS.md` y `CLAUDE.md` | Creados y publicados | Verificado: commit `08f3972`, contenido en `origin/main`. |
| **Fase 0.1** | **Completada** | Commits `08f3972`, `d3cd293` y `5c172ca`, contenidos en `origin/main`. Las transcripciones 06 a 08 de Claude Code y las conversaciones de ChatGPT siguen pendientes de exportar o aportar (ver `docs/ai-log.md`). |
| **Fase 0.2** | **Completada y publicada** | Commit `392448b3f918bed466824db495008cbd35675898` en `origin/main`: FastAPI, `GET /health`, 5 pruebas pytest, Docker, Docker Compose y `constraints.txt` (sin hashes). **Sin validación real con Stacker News.** |
| **Fase 0.3** | **En revisión de cierre** | Investigación y diseño aprobados **provisionalmente** por el propietario; documentos en `docs/nip46-*.md` y `docs/stacker-news-compatibility.md`. Las decisiones propuestas siguen **pendientes de aprobación** (ver `docs/decisions.md`). Sin cambios de código, sin dependencias nuevas y **sin commit** de esta fase. La Fase 1.0 **no está iniciada**. |

## 7. Origen y trazabilidad

- Este documento es una **síntesis proporcionada y revisada por el propietario**, redactada con asistencia de Claude Code. No es una transcripción de ChatGPT.
- No se atribuye automáticamente ninguna decisión a ChatGPT: las decisiones son del propietario.
- Las **transcripciones originales de ChatGPT no se han aportado** y siguen **pendientes**. Este documento no las sustituye. El estado se mantiene en `docs/ai-log.md`.
- Las reglas de trabajo de los agentes están en `AGENTS.md` y `CLAUDE.md`. Este documento aporta contexto de planificación y no las modifica.
