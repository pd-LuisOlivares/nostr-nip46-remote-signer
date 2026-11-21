# Contexto del proyecto

> **Origen y naturaleza de este documento.** Es una **síntesis** de discusiones mantenidas por el propietario del proyecto con ChatGPT, proporcionada y revisada por el propietario. **No es una transcripción literal** ni debe leerse como tal. Las decisiones que contiene fueron **establecidas o aprobadas por el propietario**; ChatGPT se utilizó como herramienta complementaria de análisis y no se le atribuyen decisiones. Las transcripciones originales de ChatGPT siguen pendientes de aportarse (ver §7).
>
> **Actualización (2026-11-20, revisión de cierre de la Fase 0.3, por petición del propietario).** Se actualizaron los apartados 2, 3 y 6 para reflejar el estado de las Fases 0.1, 0.2 y 0.3. Las demás secciones conservan el texto de la síntesis original.
>
> **Actualización (2026-11-20, cierre técnico de la Fase 1.0A, por petición del propietario).** Se actualizó el apartado 6 (estado) con las Fases 1.0A y 1.0B. Es un registro de estado redactado por Claude Code a partir de la evidencia (ver `docs/phase-1.0A-closure.md`); no añade decisiones ni sustituye la síntesis original.

> **Actualización (2026-11-21, B2 y B3).** Registro de estado redactado por el agente; no es una síntesis de ChatGPT. El propietario autorizó implementar el firmante NIP-46 (B2) y la API local de control (B3) y preparar la demostración real (B4). Estado: firmante y API **implementados y probados localmente** (530 pruebas; regresión con NDK 2.12.2 en red interna); **sin autenticación real con Stacker News todavía**; B4 espera una única autorización operativa (`docs/phase-1.0B-B4-gate.md`, con D-5 pendiente); B5 y B6 no autorizados. La clave Nostr vive solo en memoria y la API se protege con un token de operador (no hay JWT ni SQLite en este alcance).
>
> **Actualización (2026-11-21, cierre local de B2 a B6).** Registro de estado redactado por el agente. El propietario aprobó **JWT** para la API local (D-8, reemplaza al token de operador). Estado: firmante, API con JWT, **interfaz web** y E2E de navegador real **implementados y verificados en local** (607 pruebas; E2E Docker con NDK 2.12.2 real); **B4 (autenticación real con Stacker News) preparado y sin ejecutar**, pendiente de una única autorización operativa (`docs/phase-1.0B-B4-gate.md`, D-5: identidad de prueba dedicada y reutilizable del propietario). No se declara éxito real hasta observar una sesión autenticada en Stacker News.
>
> **Actualización (2026-11-21, compuerta de B4).** El propietario registró D-5 (identidad nueva, dedicada y reutilizable, bajo su custodia privada), el destino `https://stacker.news/signup` y su aceptación de una cuenta real de prueba. **No** autorizó aún la ejecución: la ventana de 15 minutos empieza solo con su confirmación. La compuerta, el procedimiento, los criterios PASS/FAIL/BLOCKED y las herramientas de identidad y evidencias están preparados (`docs/phase-1.0B-B4-gate.md`); B4 sigue **sin ejecutar y sin declarar completado**.
>
> **Actualización (2026-11-21, ejecución de B4).** Con autorización expresa del propietario se ejecutó la demostración real: el firmante emitió **una** firma `kind 27235` aprobada manualmente y, según la observación del propietario, **Stacker News abrió una sesión asociada a `@c5a035bf14…`** (cuenta real de prueba). Veredicto de B4: **PASS con observaciones** (`docs/decisions.md`). La validación real de B6 (repetición desde la interfaz) sigue pendiente de autorización.
>
> **Actualización (2026-11-21, cierre de jornada).** Registro redactado por el agente. Estado: B0 a B5 implementados y verificados en local; **B4 PASS con observaciones** (auditoría verificada; la sesión de Stacker News la observó el propietario); B6: E2E local y Docker aprobados, **validación real y reproducibilidad final pendientes**. El trabajo se publicó en `origin/main`. Para retomar: `docs/handoff-2026-11-21.md` (la primera actividad es cerrar B6, no reimplementar B2 a B5).

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

**Estado de la implementación (actualizado).** Desde la Fase 0.2 el repositorio contiene una base de aplicación mínima: FastAPI con `GET /health`, pruebas con pytest, Docker y Docker Compose. **Actualización (Fase 1.0B, B0 y B1):** `app/` contiene ahora el núcleo Nostr (`app/nostr/`) y `app/config.py`; **sigue sin existir** el servicio firmante, la conexión a relays, la API de control, la interfaz web, JWT (descartado por D-4: token de operador) y SQLite (descartado para el MVP por D-3). El código del firmante de laboratorio vive solo en `lab/` (no es producto).

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
| **Fase 0.3** | **Completada** (commit `ec739bd`) | Investigación y diseño en `docs/nip46-*.md` y `docs/stacker-news-compatibility.md`. Las decisiones propuestas siguen **pendientes de aprobación** (ver `docs/decisions.md`). |
| **Fase 1.0A** (laboratorio e interoperabilidad) | **Cierre técnico preparado; pendiente de aprobación del propietario. Sin commit.** | Laboratorio con NDK 2.12.2 (E1 a E7: 39 de 39 en PASS), firmante real mínimo **de laboratorio** (`lab/`), sondas de relay (`relay.primal.net:443` **GO**; `relay.nsec.app` y `relay.primal.io` NO-GO) y **observación real de Stacker News** (Compuerta B): llegaron `connect` (NIP-04), `get_public_key` y un `sign_event` del evento `kind 27235`, **denegado a propósito, sin firmas ni cuenta**. **Interoperabilidad de protocolo observada; autenticación completa pendiente.** Detalle y salvedades en `docs/phase-1.0A-closure.md`. |
| **Fase 1.0B** (producto mínimo en `app/`) | **En curso: Bloques B0 y B1 completados; B2 a B6 no autorizados** | Aprobadas D-1 a D-4, D-6 y D-7 (D-5 pendiente): dependencias `coincurve`, `cryptography`, `websockets`; `app/config.py`; clave solo en memoria; token de operador en lugar de JWT; relay `wss://relay.primal.net`. Implementado el núcleo Nostr en `app/nostr/` (claves, eventos, NIP-44, NIP-04 entrante, NIP-46 y `bunker://`) con 253 pruebas (incluido el CSV oficial completo de BIP-340). **Sin servicio firmante, API de control ni interfaz web todavía.** Detalle en `docs/decisions.md` y `docs/phase-1.0B-proposal.md` (§9: propuesta de B2).

## 7. Origen y trazabilidad

- Este documento es una **síntesis proporcionada y revisada por el propietario**, redactada con asistencia de Claude Code. No es una transcripción de ChatGPT.
- No se atribuye automáticamente ninguna decisión a ChatGPT: las decisiones son del propietario.
- Las **transcripciones originales de ChatGPT no se han aportado** y siguen **pendientes**. Este documento no las sustituye. El estado se mantiene en `docs/ai-log.md`.
- Las reglas de trabajo de los agentes están en `AGENTS.md` y `CLAUDE.md`. Este documento aporta contexto de planificación y no las modifica.
