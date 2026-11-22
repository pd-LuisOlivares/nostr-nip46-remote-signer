# OVERNIGHT RESULTS — trabajo nocturno autónomo del 2026-11-22

Segunda jornada sin supervisión, complementaria de [`NIGHTLY-REVIEW.md`](NIGHTLY-REVIEW.md). Todo quedó en **commits locales**. **NO se hizo push, ni pull request, ni se publicó nada en ningún remoto.** Este documento no contiene credenciales ni secretos y solo afirma como probado lo que se ejecutó.

## 1. Resumen ejecutivo

- Se resolvió el conflicto de puertos entre el cliente de laboratorio y el perfil demo, se cerró **P-49**, se endureció el contexto de construcción de Docker y se corrigieron cuatro pruebas Docker del laboratorio que llevaban desactualizadas desde que el modo continuo es el predeterminado.
- **P-47 y P-48 no se implementan** (no bloquean la entrega; análisis y riesgo aceptado documentados).
- Validación integral: suite completa del árbol **1044 passed, 27 skipped, 0 failed**; Docker: **14 + 5 passed** contra el código actual; **clon limpio de los commits candidatos: 1036 passed, 35 skipped, 0 failed** y stack Docker funcional con recursos exclusivos.
- **B6.2 intacto**: mismo contenedor, mismo arranque, 0 reinicios, base con el mismo resumen lógico antes y después; sin conexiones a relays ni a Stacker News.
- Quedan decisiones del propietario (§10) y el push de 6 commits locales (+ el de esta documentación).

## 2. Trabajo completado

| # | Trabajo | Commit local |
|---|---|---|
| 1 | Perfil propio del laboratorio `lab/manual/manual.env` (firmante en **18000**), documentación de servicios y puertos y prueba que impide repetir un puerto entre perfiles | `4f2c112` |
| 2 | **P-49**: contador «Reconectando, intento n de 5» (estado, esquema, interfaz) con pruebas de regresión | `1933ec7` |
| 3 | `.dockerignore`: el contexto de construcción excluye `deploy/`, `docs/`, `lab/`, `tests/` y `tools/` + prueba de coherencia con el Dockerfile | `2ffd56b` |
| 4 | Pruebas Docker del cliente de laboratorio: modo `supervised` fijado de forma explícita (4 fallos por expectativas supervisadas obsoletas; no eran defectos del producto) | `e5c2384` |
| 5 | Decisiones D-19 y estado de P-47/P-48/P-49 en `docs/decisions.md`; README | `eaa7ecb` |
| 6 | Esta documentación, `HANDOFF.md` y la trazabilidad (entrada 53) | ver §9 |
| — | Anterior (misma noche, primera tanda): `docs/NIGHTLY-REVIEW.md`, URL real del README, PASS documentado | `4629061` |

**Código funcional modificado:** solo `app/services/runtime.py`, `app/schemas/control.py` y `app/static/app.js` (P-49: un contador de solo lectura). No se tocó la criptografía, la política de firma, las aprobaciones, los límites, las esperas de reconexión ni la autenticación. **No se tocó nada de B6.2.**

## 3. Arquitectura final y puertos

Cada fila es un **proyecto Docker independiente** (contenedor, red, volumen y **base SQLite propios**; no hay bases compartidas). El cliente de laboratorio **no** forma parte de `compose.yaml`. Una sola instancia del firmante por proyecto.

| Puerto | Servicio | Perfil / proyecto | Estado en esta máquina |
|---|---|---|---|
| `8000` | Firmante (interfaz `/` + API `/api`) para **evaluación** | `deploy/demo.env`, `nip46-evaluacion` | no creado aquí (nada escucha) |
| `8001` | Firmante de la **validación real** del propietario | `deploy/continuous.env` / `b62.env`, `nostr-nip46-remote-signer` | **en marcha, intacto** |
| `18000` | Firmante de la demostración de **laboratorio** (pestaña A) | `lab/manual/manual.env`, `nip46-demo` | no creado aquí |
| `18080` | **Cliente NIP-46 de laboratorio** (pestaña B, NDK 2.12.2 real) | `lab/manual/compose.manual.yaml` | no creado aquí |
| `17777` | Relay local de laboratorio | idem | no creado aquí |

La **interfaz del firmante** está en `app/static/` y la sirve el propio firmante; el **cliente de laboratorio** está en `lab/manual/client_web/`. Con esto 8000 y 18000 ya no chocan y los cinco puertos pueden coexistir. **Sin cambiar** los puertos, volúmenes, credenciales ni contenedores de B6.2. Opciones descartadas: mover el perfil demo a otro puerto (el 8000 ya es el valor por defecto documentado) y fusionar el laboratorio en `compose.yaml` (mezcla producto y laboratorio).

## 4. Estado de P-47, P-48 y P-49

| # | Estado | ¿Bloquea la entrega? | Criterio |
|---|---|---|---|
| **P-49** | **Implementada** (`1933ec7`) | No | Cambio acotado y de solo lectura; no toca esperas ni aprobaciones |
| **P-47** (volver a emparejar con la misma clave de cliente) | **No implementada.** Riesgo aceptado: tras revocar o caducar hay que usar una clave de cliente nueva | No | Modifica la máquina de estados de `connect` (sensible) y depende de un supuesto sin verificar (si Stacker News reutiliza su clave de cliente). Necesita aprobación formal |
| **P-48** (límite propio para remitentes no autorizados) | **No implementada.** Riesgo aceptado: un remitente desconocido puede retrasar a clientes legítimos hasta que avance la ventana de 60 s; no revoca ni detiene nada | No | El límite global (120/min) se cuenta **antes** de identificar al remitente, así que un límite por remitente no impide agotarlo; solo recortaría respuestas `unauthorized`. La mitigación real exigiría filtrar en el relay o identificar antes de descifrar (cambio de diseño) |

Mejoras futuras: P-47 con URI nueva y aprobación humana (nunca recuperando la autorización anterior); P-48 solo si se rediseña la identificación previa al descifrado.

## 5. Correcciones de seguridad

- **Aplicada:** `.dockerignore` reduce el contexto de construcción (los perfiles con la credencial de demostración pública y las transcripciones ya no viajan al daemon). La imagen **no cambia** (solo copia `app/` y tres archivos); se comprobó que no contiene archivos `.env` ni `deploy/`.
- **Revisión (sin hallazgos nuevos críticos ni altos):** autenticación, sesiones, CSRF, JWT, Argon2id, SQLite, claves Nostr, límites, Docker y configuración, además de las transcripciones. Verificado de nuevo en los clones: cabeceras de seguridad, `Host` ajeno 400, login correcto 200 e incorrecto 401, identidad sin exposición de clave privada, 0 conexiones salientes, contraseña ausente de los registros.
- **No corregido (requiere decisión del propietario o cambia diseño):** correo de autoría en la historia pública (M-1), firmante B6.2 posiblemente activo y contraseña en el historial local (M-2), dependencias sin hashes y base mutable (B-2), `Cache-Control` en la página estática (B-6), límite global de login (B-4). Detalle en `NIGHTLY-REVIEW.md` §4.
- **No se leyeron ni modificaron secretos de B6.2.**

## 6. Resultados de pruebas

| Prueba | Resultado |
|---|---|
| `python -m pytest` (árbol, con E2E de navegador) | **1044 passed, 27 skipped, 0 failed** (26 de Docker sin `E2E_DOCKER` y 1 POSIX) |
| `python -m pytest -m "not e2e"` | 1017 passed, 1 skipped |
| Docker del cliente de laboratorio (`E2E_DOCKER=1`, `test_manual_client_web.py`) | primero **4 failed / 10 passed** (expectativas supervisadas obsoletas); tras fijar `SIGNER_MODE=supervised`: **14 passed** |
| Docker contra una imagen temporal del código actual: `test_docker_continuous`, `test_docker_ndk`, `test_docker_b62_profile`, `test_docker_persistence` | **5 passed** |
| `git diff --check` antes de cada commit | limpio |

No se ejecutó `test_docker_argon2_memory.py` (usa la imagen `:dev`, anterior al código actual). No hay cobertura ni análisis estático (herramientas no instaladas). Todo es **validación automatizada y local**; no se probó nada contra Stacker News ni relays públicos.

## 7. Resultado del clon limpio: **PASS**

Clon desde el repositorio local en un directorio temporal, con los commits candidatos (`HEAD eaa7ecb`, 281 archivos versionados, árbol limpio).

- `py -3.12 -m venv`, `pip install -c constraints.txt -e ".[dev]"` y `pip check`: sin errores (Python 3.12.10).
- `python -m pytest`: **1036 passed, 35 skipped, 0 failed** (2 min 15 s). Omitidas: 26 de Docker, **8 vectores NIP-44** (`lab/vendor/` no se versiona) y 1 POSIX. Es coherente con el árbol: 1044 − 8 vectores.
- Docker del perfil demo con **proyecto `nip46-nightclone`, puerto 18091 y etiqueta propia** (sin usar 8000, 8001 ni volúmenes existentes), con una construcción **sin caché**: contenedor sano; login con las credenciales del README 200 (incorrecta 401); identidad temporal sin exponer la clave; modo `continuous`; solo lectura, `cap_drop ALL`, puerto en loopback; 0 sockets salientes; el esquema incluye P-49; la imagen no contiene `deploy/` ni `docs/`.
- Limpieza: solo recursos con la etiqueta del proyecto (contenedor, volumen, red, imagen) y el directorio temporal. **Sin dependencias ocultas de la máquina del desarrollador** en lo ejecutado (el clon no tenía `.env`, `data/`, identidad B4 ni imágenes de laboratorio).
- **Limitaciones:** el clon salió del repositorio **local** (no de GitHub, porque estos commits no se publican); no se ejecutaron las pruebas Docker de laboratorio en el clon (necesitan las imágenes del laboratorio, sí verificadas en el árbol); no se probó Stacker News.

## 8. Estado de trazabilidad

- `docs/ai-log.md`: entrada **53** (esta jornada); manifiesto con la interacción 53.
- Transcripciones **50 a 53: PARCIAL** (la sesión `97ea8763…` permanecía abierta al exportar; estado final en `docs/ai-log.md`, «Estado final de la trazabilidad»). La contraseña administrativa de B6.2 se redacta al exportar y no aparece en ningún archivo.
- `python tools/ai_sessions.py check`: «trazabilidad OK» tras la última exportación (se desfasa en cuanto se añade un mensaje).

## 9. Commits locales creados (sin push)

`4629061` docs (revisión nocturna, primera tanda) · `4f2c112` fix(lab) puerto 18000 · `1933ec7` feat(ui) P-49 · `2ffd56b` chore(docker) `.dockerignore` · `e5c2384` test(e2e) modo supervisado en el laboratorio · `eaa7ecb` docs decisiones D-19 · y el commit de esta documentación (SHA en `git log`). **`origin/main` sigue en `70b4481`: nada se publicó.**

## 10. Pendientes y decisiones del propietario

1. **Push:** revisar los commits y autorizar o no su publicación.
2. **Firmante B6.2:** detenerlo desde la interfaz, **cambiar la contraseña de `b62-admin`**, y decidir si se captura la auditoría antes de reiniciar (se pierde).
3. **Correo de autoría** en la historia pública (M-1) y publicación de las transcripciones de IA (B-8).
4. **P-47** y **P-48** (§4): aprobar, rechazar o aceptar el riesgo.
5. **Organización de `deploy/`** (propuesta en `NIGHTLY-REVIEW.md` §6): marcar `continuous.env`/`b62.env` como perfiles del propietario.
6. **Cadena de suministro:** digest de la imagen base y hashes de dependencias (D-6).
7. **Evidencia sólida del PASS real:** repetir con captura sanitizada de la auditoría (autorización nueva).
8. **BLOQUEADO (requiere autorización, no otorgada):** cualquier prueba con Stacker News o relays; cualquier cambio en B6.2.

## 11. Instrucciones para retomar

1. Leer [`HANDOFF.md`](HANDOFF.md), este archivo y [`NIGHTLY-REVIEW.md`](NIGHTLY-REVIEW.md); comprobar `git status`, `git log origin/main..HEAD`, `docker ps`.
2. Revisar los commits locales: `git log --stat origin/main..HEAD`.
3. Si todo es correcto y se autoriza: `git fetch origin && git push origin main` (no hay conflictos esperados: `origin/main` no avanzó).
4. *(Superado: la trazabilidad quedó en su versión definitiva; ver `docs/ai-log.md`, «Estado final de la trazabilidad».)*
5. Resolver los puntos del §10 por orden de riesgo (2, 3, 4, 5).
6. Para probar el cliente de laboratorio: `docker compose --env-file lab/manual/manual.env -p nip46-demo -f compose.yaml -f lab/manual/compose.manual.yaml up --build -d` (contraseña inicial por entrada oculta; requiere las imágenes `nip46-lab-py:1.0a` y `nip46-lab-node:1.0a`) y abrir `http://127.0.0.1:18000` (firmante) y `http://127.0.0.1:18080` (cliente).
