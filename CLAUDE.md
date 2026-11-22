# CLAUDE.md — Instrucciones para Claude Code

@AGENTS.md

Las reglas de `AGENTS.md` (contexto, stack, arquitectura, seguridad, pruebas, dependencias, documentación, reglas entre agentes y control de versiones) aplican íntegramente a Claude Code. Este archivo solo añade particularidades operativas; no las sustituye ni las relaja.

## Particularidades operativas de Claude Code

- **Plan antes de cambios importantes:** para cambios de arquitectura, seguridad, dependencias o esquema de datos, usa el modo plan (o presenta un plan breve) y espera conformidad antes de editar.
- **Herramientas dedicadas:** usa Read/Grep/Glob/Edit/Write para leer, buscar y modificar archivos; reserva la terminal para git, pytest, docker y comandos del proyecto. El entorno principal es Windows con PowerShell.
- **Secretos:** por defecto no leas ni imprimas archivos `.env`, claves ni credenciales; trabaja con `.env.example`. La única excepción es la de `AGENTS.md` §7 (verificación específica autorizada de forma explícita, solo presencia o nombres de variables, sin exponer valores). Nunca guardes secretos ni datos personales en la memoria persistente de Claude Code.
- **Permisos y sandbox:** no uses `dangerouslyDisableSandbox` ni amplíes permisos o `allowlists` (`.claude/settings*.json`) sin autorización explícita del usuario. No crees hooks ni configuración de agente por tu cuenta.
- **Subagentes:** no lances subagentes salvo que el usuario lo pida. Si lo haces, aplican las mismas reglas y tú sigues siendo responsable de verificar y reportar sus resultados.
- **Git:** sin commits, pushes ni merges sin autorización explícita. Si el usuario autoriza un commit, el mensaje debe terminar con la línea de atribución que indique el entorno; no la inventes.
- **Cierre de tarea:** reporta archivos modificados, pruebas ejecutadas (comando y resultado real), `git diff --check`, `git status`, y los riesgos o supuestos pendientes, distinguiendo pruebas automatizadas de validación real con Stacker News. Recuerda que los archivos nuevos sin rastrear no aparecen en `git diff`: inspecciónalos directamente y no uses `git add` para verlos (`AGENTS.md` §11).
- **Registro de IA:** cuando existan `docs/ai-log.md` y `docs/ai-sessions/`, registra cada interacción relevante según `AGENTS.md` §9, **al completarla** (no la difieras), y exporta las transcripciones al cierre de cada Paso o bloque autorizado con `tools/ai_sessions.py`; antes de proponer un commit o la publicación final ejecuta `python tools/ai_sessions.py check` (sin hooks de Git) e informa los pendientes. Claude Code no garantiza acceso a su propio historial completo (p. ej. tras la compactación del contexto): si no puedes recuperar un prompt o respuesta literal, márcalo como "no recuperada" en lugar de reconstruirlo, y pide al propietario que exporte la sesión. Redacta secretos y datos sensibles antes de guardar.
- **Pruebas de integración externas:** solo dentro de una autorización con alcance definido (`AGENTS.md` §11); no uses herramientas de navegador o de red para actuar sobre Stacker News o relays fuera de ese alcance.
