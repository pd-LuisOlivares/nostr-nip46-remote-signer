# Contexto del proyecto

> **Origen y naturaleza de este documento.** Es una **síntesis** de discusiones mantenidas por el propietario del proyecto con ChatGPT, proporcionada y revisada por el propietario. **No es una transcripción literal** ni debe leerse como tal. Las decisiones que contiene fueron **establecidas o aprobadas por el propietario**; ChatGPT se utilizó como herramienta complementaria de análisis y no se le atribuyen decisiones. Las transcripciones originales de ChatGPT siguen pendientes de aportarse (ver §7).

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

**El stack está previsto, no implementado.** A la fecha de este documento el repositorio no contiene código de aplicación.

## 3. Decisiones de dirección del proyecto

Establecidas o aprobadas por el propietario:

- Organizar el desarrollo en **fases incrementales**.
- Reservar la **Fase 0.1** para configurar `AGENTS.md` y `CLAUDE.md`.
- Reservar la **Fase 0.2** para inicializar la aplicación y Docker.
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
| Git y GitHub configurados | Configurados | Informado por el propietario. El repositorio tiene remoto `origin` y ya se realizó un commit local. No se verificó el acceso a GitHub. |
| Docker Desktop y WSL 2 | Operativos | Informado por el propietario. No verificado por el agente. |
| Repositorio | Inicializado | Verificado: contiene `README.md` y `.gitignore` en el commit inicial. |
| `AGENTS.md` y `CLAUDE.md` | Creados | Verificado: commit local `08f3972`, aún sin push. |
| Fase 0.1 | En cierre documental | Pendiente de commit la documentación de trazabilidad (`docs/`). |
| Fase 0.2 | **No iniciada** | |

## 7. Origen y trazabilidad

- Este documento es una **síntesis proporcionada y revisada por el propietario**, redactada con asistencia de Claude Code. No es una transcripción de ChatGPT.
- No se atribuye automáticamente ninguna decisión a ChatGPT: las decisiones son del propietario.
- Las **transcripciones originales de ChatGPT no se han aportado** y siguen **pendientes**. Este documento no las sustituye. El estado se mantiene en `docs/ai-log.md`.
- Las reglas de trabajo de los agentes están en `AGENTS.md` y `CLAUDE.md`. Este documento aporta contexto de planificación y no las modifica.
