# Interacción 54: Revisión final de los commits locales y simplificación final de la instalación oficial (D-20), con verificación del usuario evaluador en SQLite

| Campo | Valor |
|---|---|
| Fecha del primer prompt (UTC) | 2026-11-22T12:39:42.263Z (America/Santiago = UTC-3) |
| Fase | 1.0B |
| Agente | Claude Code (extensión de VS Code, versión 2.1.330) |
| Modelo | claude-sonnet-5-5 (campo `model` de los registros de sesión) |
| Nivel de razonamiento | high (campo `effort` de los registros de sesión) |
| Sesión | 97ea8763-694e-4b53-8496-52b85c37bc64 |
| Origen de la transcripción | Archivo de sesión local de Claude Code (JSONL), extraído con `tools/ai_sessions.py`; no reconstruido |
| Hasta (UTC) | 2026-11-22T13:03:32.487Z |
| Estado | PARCIAL (la sesión de origen sigue abierta: se reexporta al cerrarla) |

**Qué contiene y qué no.** Prompts del propietario (sin las etiquetas `pasted_content`, los bloques del editor ni los recordatorios del sistema) y todo el texto visible de las respuestas de Claude Code, en orden. Las llamadas a herramientas se indican con una línea de marcador; su contenido y sus salidas **no** se incluyen (los archivos resultantes están en el repositorio y los resultados de las pruebas, en `docs/decisions.md`). **No se incluye razonamiento interno del modelo** ni contexto del sistema. Las marcas `<!-- fecha -->` son del archivo de sesión. Se omiten 8 notificaciones automáticas de tareas en segundo plano y 1 resumen(es) de continuación generado(s) por la compactación del contexto: no son mensajes del propietario ni del asistente.

**Redacción aplicada** (patrones y lectura de los hallazgos): URI `bunker://`, claves `nsec`, secretos de conexión, JWT, tokens `Bearer`, hashes de contraseña, contraseñas, correos, rutas locales, usuario local y nombre del autor. Las cadenas hexadecimales de 64 caracteres se clasifican por contexto: se conservan las claves **públicas**, los identificadores y las huellas SHA-256 necesarios para entender la evidencia (revisadas una a una) y la exportación se detiene ante cualquier duda. La ruta absoluta del proyecto se acortó a ruta relativa. Redacciones en este archivo: ruta-del-proyecto: 23, usuario-local: 7.

---

## Prompt del propietario (2026-11-22T12:39:42.263Z)

Realiza una revisión final de los 7 commits locales pendientes entre `origin/main` (`70b4481`) y `HEAD` (`9d8635b`).

No implementes nuevas funcionalidades ni modifiques el entorno B6.2.

1. Revisa `git log --stat origin/main..HEAD` y el diff acumulado.
2. Confirma que los cambios son coherentes con el alcance de la prueba técnica.
3. Revisa especialmente la nueva configuración de puertos, P-49 y `.dockerignore`.
4. Verifica que el perfil de evaluación del README funcione sin depender del entorno B6.2.
5. Comprueba que no existan secretos reales en los commits pendientes.
6. Revisa si las transcripciones PARCIAL pueden actualizarse sin incluir secretos.
7. Ejecuta las comprobaciones finales necesarias, sin repetir pruebas extensas que ya pasaron si no hubo cambios funcionales.
8. Confirma el estado de Git y si el repositorio está listo para publicar.

No hagas commit adicional salvo que sea indispensable para corregir documentación o trazabilidad. No hagas push, pull request, rebase ni force push.

Entrega un veredicto final: LISTO PARA PUSH o BLOQUEADO, con las razones concretas.

No hagas preguntas intermedias; documenta cualquier decisión que requiera al propietario.

<!-- 2026-11-22T12:39:43.923Z -->
Empiezo con el estado de Git y los commits pendientes.

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Write]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: PowerShell]*

<!-- 2026-11-22T12:40:24.200Z -->
Reviso ahora que el perfil de evaluación no comparte nada con B6.2 y ejecuto solo las pruebas rápidas relacionadas.

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Write]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Write]*

<!-- 2026-11-22T12:41:22.775Z -->
Estoy comprobando, sin imprimir el valor, que la contraseña de B6.2 no está en el árbol ni en la historia de Git.

> *[Llamada a herramienta: PowerShell]*

## Prompt del propietario (2026-11-22T12:41:25.979Z) — recibido a mitad de un turno

# SIMPLIFICACIÓN FINAL DEL REPOSITORIO — INSTALACIÓN OFICIAL

Actúa como ingeniero principal responsable de simplificar y preparar la entrega definitiva del proyecto Nostr NIP-46 Remote Signer.

## Decisión del propietario

Quiero que exista una única instalación oficial documentada en el README.

El usuario administrativo oficial será `evaluador`, utilizando las credenciales de demostración que ya están documentadas en el README.

El entorno B6.2 y su usuario `b62-admin` NO deben formar parte del procedimiento oficial de instalación ni evaluación.

Todo lo que ya no se utilice y sea innecesario para entregar, instalar, ejecutar, probar o mantener el proyecto debe identificarse y limpiarse del repositorio.

**PROHIBICIÓN ABSOLUTA: NO HACER PUSH.**

## Fase 1 — Inspección

1. Lee README, `docs/HANDOFF.md`, `docs/OVERNIGHT-RESULTS.md` y la configuración Docker.
2. Revisa los commits locales pendientes y el estado de Git.
3. Identifica exactamente cómo se crea el usuario `evaluador`.
4. Verifica que las credenciales del README correspondan al perfil de evaluación.
5. Identifica todas las referencias a `b62-admin`, B6.2, perfiles antiguos y despliegues experimentales.
6. Clasifica los archivos entre necesarios, documentación histórica, pruebas y elementos obsoletos.

No elimines archivos antes de comprender sus dependencias.

## Fase 2 — Instalación oficial

Establece como instalación oficial:

- Firmante NIP-46 en `http://127.0.0.1:8000`.
- Usuario administrativo `evaluador`.
- Contraseña de demostración definida en la configuración oficial y documentada en el README.
- Persistencia SQLite en un volumen Docker.
- Generación de identidad Nostr desde la interfaz.
- Aprobaciones manuales de `connect` y `sign_event`.
- Modo continuo, según la configuración validada.

Asegura que:

1. El comando documentado levante exactamente el entorno esperado.
2. La cuenta `evaluador` se cree correctamente en una instalación nueva.
3. La contraseña documentada funcione realmente.
4. Reiniciar el contenedor conserve el usuario y la base SQLite.
5. El inicio de sesión incorrecto sea rechazado.
6. El evaluador no necesite conocer ni utilizar `b62-admin`.
7. La instalación no dependa de archivos privados del desarrollador.

No introduzcas una contraseña administrativa universal en el código de producción. Mantén las credenciales de demostración limitadas al perfil local de evaluación, con una advertencia explícita de que deben cambiarse fuera de ese contexto.

## Fase 3 — Limpieza del repositorio

Identifica y elimina únicamente elementos comprobablemente obsoletos:

- Configuraciones de despliegue que ya no sean necesarias.
- Referencias operativas antiguas a B6.2.
- Scripts temporales sin uso.
- Duplicaciones de configuración.
- Instrucciones contradictorias del README.
- Archivos generados o temporales incorporados por error.

Conserva:

- Código funcional.
- Pruebas automatizadas relevantes.
- Cliente NIP-46 de laboratorio, si aporta a la evaluación.
- Herramientas de trazabilidad de IA.
- Historial de decisiones técnicas.
- Evidencia de validación real con Stacker News.
- Documentación exigida por la prueba técnica.

No borres ni reescribas transcripciones históricas de IA únicamente por mencionar B6.2. Si contienen secretos, redacta esos secretos preservando la trazabilidad.

No elimines archivos necesarios para reproducir pruebas o comprender decisiones anteriores.

Documenta los archivos eliminados y por qué ya no se necesitan.

## Fase 4 — Cliente de laboratorio

Mantén el cliente NIP-46 de laboratorio como herramienta complementaria si resulta útil.

Verifica que:

- No compita con el puerto 8000.
- No requiera levantar una segunda instancia del firmante para probar el perfil oficial, salvo que exista una razón técnica demostrable.
- Sus instrucciones sean claras y opcionales.
- No dependa de B6.2.

Si integrarlo con la instalación oficial requiere cambios importantes, conserva el laboratorio aislado y documenta esa separación. No hagas una reestructuración innecesaria.

## Fase 5 — Validación integral

Ejecuta pruebas en un entorno completamente aislado:

1. Instalación desde un directorio limpio.
2. Construcción Docker sin caché.
3. Inicio del perfil oficial en un puerto de prueba alternativo, sin ocupar el 8000 real.
4. Login exitoso con `evaluador` y la contraseña documentada.
5. Rechazo de contraseña incorrecta.
6. Persistencia del administrador tras reiniciar el contenedor.
7. Generación de identidad Nostr.
8. Pruebas automatizadas completas.
9. Comprobación de que no existen conflictos entre perfiles.
10. Revisión de secretos y trazabilidad.

No realices conexiones externas a Stacker News ni relays sin autorización.

No modifiques el entorno B6.2 existente.

## Fase 6 — Documentación

Actualiza el README para que presente:

1. Requisitos previos.
2. Clonación del repositorio.
3. Configuración mínima.
4. Comando único de inicio.
5. URL de acceso.
6. Usuario y contraseña de demostración.
7. Generación de identidad Nostr.
8. Inicio y detención del firmante.
9. Obtención de URI bunker.
10. Prueba opcional con el cliente de laboratorio.
11. Prueba con Stacker News.
12. Ejecución de tests.
13. Detención y limpieza segura de recursos.

El README debe

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

<!-- 2026-11-22T12:42:41.446Z -->
Estoy ejecutando la limpieza por pasos: ya inventarié referencias a B6.2 y dependencias; ahora retiro los perfiles B6.2 y adapto las pruebas que dependían de ellos.

> *[Llamada a herramienta: Edit — tests\test_config.py]*

> *[Llamada a herramienta: Edit — tests\e2e\test_docker_continuous.py]*

> *[Llamada a herramienta: Edit — tests\e2e\test_docker_continuous.py]*

> *[Llamada a herramienta: Edit — tests\e2e\test_docker_continuous.py]*

> *[Llamada a herramienta: Write — tests\test_deploy_profile.py]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Write]*

> *[Llamada a herramienta: Write — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\97ea8763-694e-4b53-8496-52b85c37bc64\scratchpad\splice_readme2.py]*

> *[Llamada a herramienta: Edit — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\97ea8763-694e-4b53-8496-52b85c37bc64\scratchpad\splice_readme2.py]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Edit — README.md]*

> *[Llamada a herramienta: Edit — README.md]*

> *[Llamada a herramienta: Edit — README.md]*

> *[Llamada a herramienta: Edit — README.md]*

> *[Llamada a herramienta: Edit — compose.yaml]*

> *[Llamada a herramienta: Edit — compose.yaml]*

> *[Llamada a herramienta: Edit — .env.example]*

> *[Llamada a herramienta: Edit — .env.example]*

> *[Llamada a herramienta: Edit — deploy\demo.env]*

> *[Llamada a herramienta: Edit — lab\manual\compose.manual.yaml]*

> *[Llamada a herramienta: Edit — lab\manual\manual.env]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Edit — deploy\demo.env]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Edit — tests\test_deploy_profile.py]*

<!-- 2026-11-22T12:45:02.804Z -->
Ahora la suite completa (sin Docker) para confirmar que la limpieza no rompió nada, y en paralelo las decisiones (D-20).

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Edit — docs\HANDOFF.md]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T12:45:45.182Z -->
Sigo esperando la suite completa en segundo plano mientras termino la documentación; en cuanto termine, hago el commit y el clon limpio.

> *[Llamada a herramienta: Monitor]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T12:45:56.098Z -->
Todavía corre la suite completa en segundo plano. Hasta ahora quedaron hechos, sin commit:

- Retiré `deploy/b62.env`, `deploy/continuous.env`, `deploy/import_admin_db.py` y `tests/e2e/test_docker_b62_profile.py`, y reescribí las pruebas del perfil de despliegue.
- Reorganicé el README como una única «Instalación oficial» con los 13 pasos que pediste.
- Documenté la decisión D-20 (archivos eliminados y por qué) y actualicé el HANDOFF.

Cuando termine la suite sigo con el commit local, el clon limpio con Docker sin caché en un puerto alternativo y la trazabilidad. No haré push.

## Prompt del propietario (2026-11-22T12:46:30.499Z)

## REQUISITO OBLIGATORIO — VALIDACIÓN DEL USUARIO `evaluador` EN SQLITE

Antes de considerar finalizada la simplificación del repositorio, debes garantizar que el usuario `evaluador` exista y funcione en la base de datos SQLite de la instalación oficial descrita en el README.

### Validaciones obligatorias

1. Identifica la base SQLite utilizada por el perfil oficial de evaluación y verifica su volumen persistente.
2. Consulta la tabla de administradores y confirma que existe el usuario `evaluador`, que está activo y que tiene un hash Argon2id válido.
3. Comprueba que la contraseña de demostración documentada en el README permite iniciar sesión mediante el endpoint real de autenticación.
4. Verifica que una contraseña incorrecta sea rechazada.
5. Reinicia únicamente el contenedor aislado de pruebas y confirma que `evaluador` sigue existiendo y puede autenticarse.
6. Comprueba que la inicialización sea idempotente: reiniciar o volver a ejecutar el despliegue no debe duplicar ni sobrescribir administradores existentes.
7. Verifica qué sucede cuando SQLite ya contiene otro administrador, pero no contiene a `evaluador`.

### Comportamiento esperado

- En una instalación nueva, `evaluador` debe crearse automáticamente mediante el procedimiento oficial de inicialización.
- Su contraseña debe almacenarse únicamente como hash Argon2id.
- En reinicios posteriores, la cuenta debe mantenerse sin regenerarse ni cambiar su contraseña.
- No debe depender del usuario `b62-admin` ni de la base SQLite de B6.2.
- Si una base existente no contiene `evaluador`, documenta un procedimiento explícito y seguro para provisionarlo, sin eliminar usuarios ni sobrescribir credenciales.
- No implementes un restablecimiento automático de contraseñas al iniciar el contenedor.

### Seguridad

La contraseña de demostración solo debe utilizarse en el perfil local de evaluación. No debe quedar incorporada como credencial universal del código de producción.

### Evidencia requerida

Documenta:

- Nombre de la base y volumen utilizado.
- Existencia y estado activo de `evaluador`.
- Login correcto: HTTP 200.
- Login incorrecto: HTTP 401.
- Persistencia después del reinicio.
- Resultado de la prueba de idempotencia.
- Resultado del escenario con otro administrador preexistente.

No imprimas hashes completos ni secretos en los informes.

### Restricciones

No modifiques la base SQLite, los usuarios, el contenedor ni los volúmenes de B6.2.

Realiza todas las pruebas sobre una instalación nueva y aislada.

Puedes corregir el mecanismo de aprovisionamiento del perfil oficial si encuentras un defecto, agregando pruebas de regresión.

No hagas push.

**Esta validación es un requisito de aceptación obligatorio para declarar que la instalación oficial está lista para entrega.**

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Edit — README.md]*

> *[Llamada a herramienta: Edit — tests\test_deploy_profile.py]*

> *[Llamada a herramienta: PowerShell]*

<!-- 2026-11-22T12:47:09.580Z -->
Reformulo esa frase para que el `down -v` lleve el proyecto y la advertencia de destrucción.

> *[Llamada a herramienta: Edit — README.md]*

> *[Llamada a herramienta: PowerShell]*

## Prompt del propietario (2026-11-22T12:47:14.471Z) — recibido a mitad de un turno

Continúa con el trabajo en curso y deja finalizar la suite completa.

Antes de declarar PASS en el clon limpio y realizar el commit local, incorpora como requisito obligatorio verificar el usuario `evaluador` en la SQLite del perfil oficial:

1. Confirma que existe, está activo y tiene contraseña almacenada con Argon2id.
2. Verifica login HTTP 200 con las credenciales del README y HTTP 401 con contraseña incorrecta.
3. Reinicia el contenedor aislado y verifica que el usuario y su contraseña persisten.
4. Comprueba que reiniciar no duplica ni sobrescribe el administrador.
5. Comprueba el escenario de una base existente con otro administrador y sin `evaluador`. Si el sistema no lo crea automáticamente, documenta un procedimiento seguro para incorporarlo sin borrar datos.
6. Confirma que la base utilizada corresponde al volumen de la instalación oficial y no a B6.2.

Si detectas errores, corrígelos y agrega pruebas de regresión antes del commit.

Incluye evidencia resumida de estas verificaciones en el informe final.

No interrumpas la suite actual, no modifiques B6.2 y no hagas push.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\97ea8763-694e-4b53-8496-52b85c37bc64\scratchpad\validate_evaluador.py]*

> *[Llamada a herramienta: Edit — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\97ea8763-694e-4b53-8496-52b85c37bc64\scratchpad\validate_evaluador.py]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Monitor]*

<!-- 2026-11-22T12:48:37.839Z -->
La validación sigue corriendo en Docker (la construcción sin caché tarda unos minutos). Cuando termine reviso cada comprobación, y solo entonces haré el commit local y el resto de la trazabilidad; no haré push.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — docs\evidence\evaluador-instalacion-oficial-2026-11-22.md]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T12:52:01.740Z -->
Commit local `657c876` hecho. Ahora, el clon limpio del commit: instalación con pip, suite completa y la herramienta de validación Docker ejecutada desde ese clon.

> *[Llamada a herramienta: Write — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\97ea8763-694e-4b53-8496-52b85c37bc64\scratchpad\clone_final.ps1]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Monitor]*

<!-- 2026-11-22T12:52:20.805Z -->
El clon limpio está corriendo (pip, suite completa y la validación Docker desde el clon). Cuando termine, registro la trazabilidad y entrego el veredicto; no haré push.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Monitor]*

<!-- 2026-11-22T12:57:50.770Z -->
Mientras termina la suite completa del árbol, preparo el registro de trazabilidad (interacción 54).

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\97ea8763-694e-4b53-8496-52b85c37bc64\scratchpad\entry54.py]*

> *[Llamada a herramienta: Edit — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\97ea8763-694e-4b53-8496-52b85c37bc64\scratchpad\entry54.py]*

<!-- 2026-11-22T12:58:13.290Z -->
Espero el resultado final de la suite del árbol para completar las cifras del registro.

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T12:58:15.433Z -->
Todavía no terminó; el monitor me avisará.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T13:01:02.330Z -->
Exportadas las transcripciones (parciales, redactadas). Verifico con `scan`, `check` y la guarda de la contraseña de B6.2.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T13:01:14.157Z -->
Trazabilidad OK y sin hallazgos. Hago el commit local de documentación y trazabilidad.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-22T13:01:37.302Z -->
**Veredicto: LISTO PARA PUSH (técnicamente), a la espera de tu autorización. No hice push, pull request, rebase ni force push.** `origin/main` sigue en `70b4481` y hay 9 commits locales por delante; el último es `1a44810`. El árbol de trabajo está limpio.

El mensaje con las fases de la simplificación llegó **truncado** («El README debe…»). Apliqué los 13 puntos de README que enumerabas, pero conviene que revises si faltaba algo en la parte cortada.

## Instalación oficial
- **Instalación única:** `docker compose --env-file deploy/demo.env -p nip46-evaluacion up --build -d` abre el firmante en `http://127.0.0.1:8000` con el usuario `evaluador`. Corre en modo continuo y cada `connect` y `sign_event` sigue requiriendo aprobación manual.
- **README:** reescrito con los 13 pasos y con el procedimiento seguro para el caso de una base con otro administrador.
- **Retirado del árbol:** `deploy/b62.env`, `deploy/continuous.env`, `deploy/import_admin_db.py` y `tests/e2e/test_docker_b62_profile.py`.
  - Siguen en el historial (`git show 70b4481:deploy/b62.env`).
  - Motivos en `docs/decisions.md` D-20.
- **Se conserva:** el código (incluido el modo `supervised`), el cliente de laboratorio, la trazabilidad de IA, las decisiones y la evidencia de la validación real.
- **Cliente de laboratorio:** aislado y opcional, sin competir por el 8000. Mantiene su propio firmante porque el oficial solo admite relays `wss://` y el relay local es `ws://`.
- **`app/`:** sin cambios.

## Verificación obligatoria de `evaluador`
Ejecutada en Docker aislado (puertos 18095–18097, recursos nuevos, build sin caché). Resultado: **36 comprobaciones, 0 fallidas**, tanto sobre el índice previo al commit como desde un clon limpio del commit.

| Comprobación | Resultado |
|---|---|
| Base y volumen | `/data/nip46.db`, permisos `0600`, volumen del proyecto aislado (no el de B6.2) |
| Usuario | 1 fila: `evaluador`, activo, hash Argon2id (`m=65536,t=3,p=4`), sin la contraseña dentro |
| Login con las credenciales del README | HTTP 200 |
| Contraseña errónea o usuario inexistente | HTTP 401 |
| Reinicio del contenedor aislado | misma fila, login 200 |
| Idempotencia | repetir `up` no recrea nada; recrear con otra `ADMIN_PASSWORD` en el entorno deja la fila idéntica y esa otra contraseña da 401 |
| Base con otro administrador | arranca sin error, **no** crea `evaluador` (401), la fila preexistente queda idéntica y sigue entrando |
| Procedimiento documentado (`-p nip46-evaluacion-2`, otro puerto) | `evaluador` se crea y entra (200); la base anterior queda intacta |

No encontré defectos de aprovisionamiento. El esquema admite un solo administrador (D-9), así que una base con otro administrador nunca recibirá `evaluador`. No hay restablecimiento automático de contraseñas. Agregué pruebas de regresión para todo esto en `tests/test_deploy_profile.py`.

Evidencia en `docs/evidence/evaluador-instalacion-oficial-2026-11-22.md`. La herramienta reutilizable es `tools/validate_official_install.py`.

## Pruebas
- **Suite completa del árbol:** 1033 passed, 26 skipped, 0 failed. Sin e2e: 1006 passed, 1 skipped.
- **Clon limpio del commit:** `pip check` sin errores y 1025 passed, 34 skipped, 0 failed. Los omitidos son 8 vectores NIP-44 que el clon no trae, 1 prueba de permisos POSIX y 25 de Docker.
- **Higiene:** `git diff --check` limpio y `git status` limpio. Todo lo que cree en Docker y en `%TEMP%` quedó eliminado.
- **Qué no es esto:** son pruebas automatizadas y locales. No se contactó con Stacker News ni con relays y el firmante no se inició.

## Seguridad
- La contraseña de `b62-admin` no está en el árbol ni en la historia (17 commits).
- Sin patrones de secretos en lo añadido. Los avisos del escáner eran contraseñas de juguete de las pruebas.
- **B6.2 intacto:** mismo contenedor, mismo arranque (`04:47:20Z`), 0 reinicios, sano. No toqué su base, volumen ni credenciales.

## Trazabilidad
Las transcripciones 50–54 son **parciales** porque la sesión sigue abierta. `check` dio «OK» justo antes del commit y volverá a marcar la 54 como desactualizada con cada mensaje nuevo. Hay que reexportarlas al cerrar la sesión.

## Decisiones tuyas
1. **Push:** autorizarlo o no.
2. **B6.2:** detener su firmante y cambiar la contraseña de `b62-admin`. Está en el historial local de esta sesión, fuera del repositorio. También decidir qué hacer con su contenedor, volumen e imagen.
3. **Historia pública:** el correo de autoría (M-1) y la publicación de las transcripciones (B-8).
4. **Pendientes de siempre:** P-47 y P-48, dependencias sin hashes y base de imagen mutable (D-6). También la evidencia técnica de la validación real, que solo tú puedes aportar.

## Prompt del propietario (2026-11-22T13:03:09.118Z)

# PUBLICACIÓN FINAL — NIP-46

Autorizo realizar el push de los 9 commits locales pendientes hasta `1a44810` a `origin/main`, únicamente si se cumplen todas las condiciones siguientes.

1. Verifica que `HEAD` sea `1a44810` o un commit posterior creado exclusivamente para cerrar documentación y trazabilidad.
2. Confirma que el árbol de trabajo esté limpio y que el remoto no haya avanzado.
3. Revisa el diff acumulado y los archivos incluidos para confirmar ausencia de secretos privados.
4. Comprueba que la instalación oficial del README utiliza `evaluador`, puerto 8000 y SQLite persistente.
5. Conserva las evidencias de las 36 validaciones del administrador y del clon limpio.
6. Actualiza las transcripciones de IA hasta donde permita la sesión actual, redactando secretos. Mantén PARCIAL cuando corresponda y no declares completa una sesión abierta.
7. Ejecuta `python tools/ai_sessions.py check` y `git diff --check`.
8. Si las verificaciones pasan, realiza un push normal a `origin/main`, sin force push.
9. Confirma que `HEAD` y `origin/main` coinciden.

No implementes nuevas funcionalidades, no modifiques B6.2 y no alteres bases de datos ni volúmenes existentes.

Si detectas secretos, conflictos de Git o fallas de integridad, detente sin hacer push.

Entrega el SHA publicado, el resultado de las verificaciones y cualquier pendiente de trazabilidad.

<!-- 2026-11-22T13:03:15.171Z -->
Verifico primero las condiciones (HEAD, árbol limpio, remoto sin avanzar, secretos, README) y no hago push hasta que todas pasen.

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Bash]*
