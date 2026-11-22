# Evidencia: usuario `evaluador` en la SQLite de la instalación oficial (2026-11-22)

**Tipo de validación:** validación **local en Docker aislado** (no es una validación real con Stacker News). Sin conexiones a relays ni a Stacker News (no se inició el firmante). Sin secretos: no se imprimieron contraseñas, hashes completos ni tokens.

**Cómo se ejecutó:** `python -I -X utf8 tools/validate_official_install.py <raiz-del-repositorio> <evidencia.json>` sobre una exportación del índice de Git del cambio D-20 (sin los perfiles de B6.2), con recursos **nuevos y exclusivos** (proyectos `nip46-evalcheck`, `nip46-evalcheck2` y `nip46-evaluacion-2`; puertos 18095 a 18097; imagen `nostr-nip46-remote-signer:evalcheck`). Las credenciales se leyeron **de la tabla del README** y se comprobó que coinciden con `deploy/demo.env`. Al terminar se eliminaron solo esos contenedores, volúmenes e imagen (verificados por etiqueta de proyecto).

**Resultado: 36 comprobaciones, 0 fallidas.**

| Requisito | Evidencia |
|---|---|
| Base y volumen | Archivo `/data/nip46.db` (permisos `0600`) en el volumen `nip46-evalcheck_app_data`, montado en `/data`; **no** es el volumen de B6.2 (`nostr-nip46-remote-signer_app_data`). El volumen de un proyecto oficial real sería `nip46-evaluacion_app_data` |
| Existencia, estado y hash | Tabla `admins` con **1** fila: `id=1`, `username=evaluador`, `is_active=1`, hash **Argon2id** (`m=65536,t=3,p=4`, 97 caracteres); el contenido de la base no contiene la contraseña. Registro: `admin_bootstrap result=created`, sin contraseña |
| Login correcto | `POST /api/auth/login` con las credenciales del README → **HTTP 200** |
| Login incorrecto | Contraseña errónea → **HTTP 401**; usuario inexistente → **HTTP 401** |
| Persistencia tras reiniciar | `docker restart` solo del contenedor aislado: misma fila (id, usuario, estado, hash, fechas de creación y actualización idénticos), login **200**, contraseña errónea **401**; registro `admin_bootstrap result=exists` |
| Idempotencia | Repetir `up -d` no recrea el contenedor ni cambia nada; `up -d --force-recreate` con **otra** `ADMIN_PASSWORD` en el entorno deja la fila idéntica (1 administrador): la contraseña del README sigue valiendo (200) y la del entorno no (401); `down` (sin `-v`) y `up` conservan la base |
| Otro administrador, sin `evaluador` | Base creada con `otroadmin`; al arrancar después con el perfil oficial: arranca sin error (`result=exists`), **no se crea** `evaluador` (login **401**), la fila de `otroadmin` queda **idéntica** y sigue entrando (**200**). Es el diseño de D-9: el esquema admite **un solo** administrador (`id = 1`) y nunca sobrescribe ni restablece contraseñas al arrancar |
| Procedimiento seguro | Documentado en el README (paso 6): proyecto y volumen **nuevos**, p. ej. `APP_PORT=8002 docker compose --env-file deploy/demo.env -p nip46-evaluacion-2 up --build -d`. Verificado con el nombre del README: `evaluador` se crea y entra (**200**) en un volumen propio y la base anterior queda intacta |
| B6.2 | Contenedor `c84dd353f674…`, arranque `2026-11-22T04:47:20Z`, 0 reinicios, sano: **idéntico antes y después**; no se tocó su base, volumen ni credenciales |

**Pruebas automatizadas de regresión agregadas** (`tests/test_deploy_profile.py`): creación con Argon2id y contraseña ausente del hash; idempotencia (misma contraseña, otra distinta o ninguna: la fila no cambia); persistencia al «reiniciar» sobre la misma base; base con otro administrador (no se crea `evaluador`, la fila no cambia, el esquema impide un segundo administrador); y que el README documenta el procedimiento.

**Defectos encontrados:** ninguno en el aprovisionamiento. No se modificó el código de `app/`.
**Límite:** la validación se ejecutó sobre el índice previo al commit; el commit solo añade esta evidencia y la herramienta.
