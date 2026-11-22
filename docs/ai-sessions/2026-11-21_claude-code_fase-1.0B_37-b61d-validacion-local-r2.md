# Interacción 37: B6.1D y B6.1D-R2: validación manual local, diagnóstico y propuesta de cliente de demostración en el navegador

| Campo | Valor |
|---|---|
| Fecha del primer prompt (UTC) | 2026-11-21T21:05:15.021Z (America/Santiago = UTC-3) |
| Fase | 1.0B |
| Agente | Claude Code (extensión de VS Code, versión 2.1.329) |
| Modelo | claude-sonnet-5-5 (campo `model` de los registros de sesión) |
| Nivel de razonamiento | high (campo `effort` de los registros de sesión) |
| Sesión | 35f0f3c1-13e9-47b9-832f-f6252cd2166f |
| Origen de la transcripción | Archivo de sesión local de Claude Code (JSONL), extraído con `tools/ai_sessions.py`; no reconstruido |
| Hasta (UTC) | 2026-11-21T21:26:07.744Z |
| Estado | COMPLETA (contenido visible) |

**Qué contiene y qué no.** Prompts del propietario (sin las etiquetas `pasted_content`, los bloques del editor ni los recordatorios del sistema) y todo el texto visible de las respuestas de Claude Code, en orden. Las llamadas a herramientas se indican con una línea de marcador; su contenido y sus salidas **no** se incluyen (los archivos resultantes están en el repositorio y los resultados de las pruebas, en `docs/decisions.md`). **No se incluye razonamiento interno del modelo** ni contexto del sistema. Las marcas `<!-- fecha -->` son del archivo de sesión.

**Redacción aplicada** (patrones y lectura de los hallazgos): URI `bunker://`, claves `nsec`, secretos de conexión, JWT, tokens `Bearer`, hashes de contraseña, contraseñas, correos, rutas locales, usuario local y nombre del autor. Las cadenas hexadecimales de 64 caracteres se clasifican por contexto: se conservan las claves **públicas**, los identificadores y las huellas SHA-256 necesarios para entender la evidencia (revisadas una a una) y la exportación se detiene ante cualquier duda. La ruta absoluta del proyecto se acortó a ruta relativa. Redacciones en este archivo: ruta-del-proyecto: 4, usuario-local: 2.

---

## Prompt del propietario (2026-11-21T21:05:15.021Z)

# B6.1D — VALIDACIÓN FUNCIONAL LOCAL ANTES DE PUBLICAR

Actúa como ingeniero senior de QA, Python/FastAPI y seguridad de aplicaciones.

Continuamos el proyecto Nostr NIP-46 Remote Signer.

B6.1C obtuvo PASS con 815 pruebas aprobadas. P-35, P-36, P-37, P-38, P-41 y P-42 están corregidos.

El propietario del proyecto ha decidido probar manualmente toda la aplicación local antes de autorizar cualquier publicación.

## OBJETIVO

Levantar la aplicación desde el árbol de trabajo actual y comprobar que los principales flujos funcionan de extremo a extremo.

La prueba debe combinar verificaciones automatizadas con una demostración manual supervisada por el propietario.

No hacer commit ni push.

No conectar con Stacker News ni relays públicos.

## 1. Preparación

Leer AGENTS.md, CLAUDE.md, README.md y los informes B6.1A, B6.1B y B6.1C.

Verificar el estado de Git y preservar todos los cambios pendientes.

Identificar el mecanismo correcto de arranque local y las dependencias necesarias.

No utilizar ni leer la identidad privada de B4.

## 2. Levantar la aplicación

Utilizar Docker Compose con el código actual.

Si no existe una base SQLite local de prueba, inicializarla mediante el mecanismo documentado.

Crear un administrador exclusivamente de prueba, con una contraseña temporal segura.

No publicar ni registrar la contraseña.

No utilizar credenciales reales.

Verificar:

- Contenedor healthy.
- SQLite inicializada.
- Usuario administrador disponible.
- Interfaz accesible en localhost.
- JWT generado al autenticarse.
- Cookie HttpOnly.
- Ausencia de errores relevantes.

No borrar bases existentes ni volúmenes del propietario.

## 3. Comprobación manual del login

Dejar la aplicación accesible y proporcionar al propietario:

- URL local exacta.
- Nombre de usuario de prueba.
- Procedimiento seguro para obtener o configurar la contraseña sin exponerla en la conversación.
- Instrucciones para ingresar desde su navegador.

Esperar confirmación del propietario de que pudo iniciar sesión.

No declarar PASS manual sin esa confirmación.

## 4. Administración del firmante

Guiar al propietario por la interfaz actual.

Comprobar:

- Estado inicial.
- Creación o importación de identidad Nostr efímera de prueba.
- Visualización de clave pública.
- Inicio y detención del firmante.
- Estado de conexión.
- Gestión de solicitudes.
- Cierre de sesión.

Nunca mostrar claves privadas en logs, capturas o informes.

No importar la identidad real de B4.

## 5. Prueba NIP-46 completamente local

Utilizar exclusivamente un relay local y un cliente de pruebas local.

Comprobar:

- Solicitud connect.
- get_public_key.
- ping, si está soportado por el cliente de prueba.
- sign_event.
- Aparición de solicitud pendiente.
- Aprobación humana desde el navegador.
- Revalidación P-38.
- Resultado P-42: Firmada correctamente.
- Recepción de respuesta por el cliente local.
- Rechazo de una solicitud inválida.
- Ausencia de firmas automáticas.

El propietario debe aprobar manualmente al menos una solicitud válida.

No simular su aprobación ni sustituirla por un bypass de API.

## 6. Persistencia y seguridad

Comprobar:

- Logout y nuevo login.
- Persistencia del administrador tras reiniciar Docker.
- Ausencia de contraseñas o JWT en respuestas visibles al JavaScript.
- Funcionamiento de CSRF.
- Ausencia de solicitudes externas inesperadas.
- Ausencia de secretos en logs.

No realizar pruebas destructivas sobre datos existentes.

## 7. Evidencias

Guardar únicamente evidencias locales sanitizadas.

Registrar:

- Comandos utilizados.
- Estado del contenedor.
- Resultados de cada comprobación.
- Capturas de pantalla sin secretos, cuando sean útiles.
- Confirmaciones manuales del propietario.
- Problemas encontrados.

No registrar contraseñas, JWT, claves privadas ni URI bunker completas.

## 8. Restricciones

No conectar con Stacker News.

No conectar con relays públicos.

No utilizar la identidad de B4.

No ejecutar firmas Nostr reales fuera del entorno local.

No modificar AGENTS.md ni CLAUDE.md.

No hacer commit ni push.

No modificar código salvo correcciones menores indispensables para poder realizar la prueba; si aparece un defecto de seguridad o un cambio funcional relevante, detenerse y reportarlo antes de corregir.

## 9. Cierre

Entregar una matriz de resultados:

- PASS automatizado.
- PASS confirmado manualmente.
- FAIL.
- NO PROBADO.

Distinguir claramente los resultados automatizados de las acciones realizadas por el propietario.

Al terminar, dejar la aplicación disponible para revisión si el propietario así lo solicita, sin dejar conexiones externas activas.

No avanzar a publicación ni B6.2.

Esperar autorización expresa.

<!-- 2026-11-21T21:06:03.714Z -->
Empiezo verificando el estado real: Git, Docker, imágenes locales, puertos y el cliente de prueba disponible.

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Read]*

> *[Llamada a herramienta: Grep]*

> *[Llamada a herramienta: Grep]*

<!-- 2026-11-21T21:06:43.292Z -->
Creo los archivos de apoyo de la demostración local (override de Compose con relay local aislado, cliente de pruebas y comprobaciones automáticas), todo bajo `lab/manual/`.

> *[Llamada a herramienta: Write — lab\manual\compose.manual.yaml]*

> *[Llamada a herramienta: Write — lab\manual\local_client.py]*

> *[Llamada a herramienta: Bash]*

> *[Llamada a herramienta: Write — lab\manual\check_live.py]*

<!-- 2026-11-21T21:07:57.929Z -->
Genero la contraseña de prueba directamente a un archivo local fuera del repositorio (sin imprimirla) y levanto la pila con Docker Compose.

> *[Llamada a herramienta: Write — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\35f0f3c1-13e9-47b9-832f-f6252cd2166f\scratchpad\manual_up.ps1]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: PowerShell]*

<!-- 2026-11-21T21:09:26.951Z -->
La aplicación está levantada y las **28 comprobaciones automatizadas de solo lectura pasaron (28/28)**. Ahora necesito que usted haga la parte manual; no declaro nada como «PASS manual» hasta que me lo confirme.

## Datos de acceso
- **URL:** http://127.0.0.1:8000. Solo escucha en su equipo.
- **Usuario:** `admin-manual`. Es solo de prueba.
- **Contraseña:** está en un archivo que solo puede leer su usuario de Windows, fuera del repositorio, y yo no la he leído ni mostrado. Para ingresar, en **su** PowerShell:
  ```powershell
  Get-Content "$env:USERPROFILE\.nip46-manual\admin_password.txt" | Set-Clipboard
  ```
  Pegue con Ctrl+V en el campo Contraseña (no se ve en pantalla). Después limpie el portapapeles con `Set-Clipboard -Value $null`, y el historial con Win+V si lo tiene activado.

## Qué hay detrás
- Contenedor del producto, construido desde el árbol de trabajo actual, con su base SQLite en el volumen `nip46-manual_app_data`.
- Relay local del laboratorio, con puerto solo en `127.0.0.1:17777`. No hay Internet, ni Stacker News, ni relays públicos.
- La cuenta se creó en el primer arranque y luego recreé el contenedor **sin** la contraseña inicial: la cuenta persistió (`exists`).
- No toqué otros volúmenes ni la identidad de B4.

## Su recorrido manual, en orden
1. **Login.** Ingrese con el usuario y la contraseña. Debería ver el panel.
2. **Estado inicial.** Clave pública «—», firmante «Detenido», y «Iniciar firmante» desactivado.
3. **Identidad.** Pulse «Crear identidad temporal» y vea la clave pública (64 hex). No importe ninguna clave real.
4. **Firmante.** Pulse «Iniciar firmante» y espere «Listo»; el relay debe decir `relay`.
5. **URI.** Pulse «Emitir URI de un solo uso» y luego «Copiar».
6. **Cliente local.** En su terminal, desde la raíz del repositorio:
   ```powershell
   .\.venv\Scripts\python.exe lab\manual\local_client.py --evidence "$env:USERPROFILE\.nip46-manual\resultado_cliente.json"
   ```
   Pegue la URI cuando la pida (no se muestra). El programa le irá indicando cada paso:
   - **[1/6]** Aparece una solicitud «Conexión de un cliente». **Apruébela.**
   - Después hace solo `get_public_key` y `ping`, y envía dos `sign_event` inválidos. Estos deben rechazarse solos, **sin tarjeta** en el navegador.
   - **[3/6]** Aparece una tarjeta de firma con las 11 comprobaciones en verde. **No la apruebe todavía**: el programa comprueba 8 s que nadie firma solo.
   - **[4/6]** **Ahora apruebe**, con rapidez: la ventana del firmante en esta demo es de 30 s. Debe aparecer «Firmada correctamente» y el banner «Firma realizada correctamente».
   - **[5/6]** Envía otra solicitud válida y le pedirá **esperar ≥ 35 s antes de aprobar**. Al aprobar tarde debe verse «Rechazada al firmar: la política dejó de cumplirse», sin firma.
7. **Cierre.** Pulse «Detener» (el motivo debe decir «detenido por el operador»), luego «Cerrar sesión» y vuelva a ingresar.

## Qué necesito de vuelta
- Si pudo iniciar sesión.
- Si cada paso se vio como lo describo; en particular los textos de los pasos 5 y 6, y cualquier cosa rara.
- El resumen final del cliente (sale como «N de N comprobaciones PASS», sin URI ni claves).

Cuando me lo confirme, hago el resto: persistencia tras `docker compose restart`, revisión final de registros y conexiones, evidencias sanitizadas y la matriz de resultados. Si algo falla en su recorrido, no corrijo nada del producto: lo reporto primero.

## Prompt del propietario (2026-11-21T21:22:47.416Z)

# B6.1D-R2 — VALIDACIÓN LOCAL COMPLETA DESDE EL NAVEGADOR

Continuamos el proyecto Nostr NIP-46 Remote Signer.

El propietario identificó una diferencia importante entre las pruebas técnicas actuales y la experiencia esperada del usuario final.

El producto es un firmante remoto NIP-46. Sus usuarios deben poder administrar identidades, conectar aplicaciones compatibles y aprobar firmas desde una interfaz web, sin ejecutar scripts de Python ni comandos de PowerShell durante el uso cotidiano.

## Objetivo

Permitir una validación funcional local, de extremo a extremo, utilizando exclusivamente navegadores para las acciones del usuario.

Mantener el producto como firmante remoto NIP-46. No convertirlo en un cliente Nostr general.

## 1. Diagnóstico previo obligatorio

Antes de implementar cambios:

- Leer AGENTS.md y CLAUDE.md.
- Revisar README y los informes B6.1A/B/C.
- Revisar los resultados manuales de B6.1D.
- Investigar las respuestas anticipadas del cliente local.
- Confirmar mediante auditoría si ocurrió alguna firma sin aprobación humana.
- Distinguir errores del producto y del cliente de laboratorio.

Si se confirma una firma sin autorización, detenerse y reportar el problema como bloqueante.

No modificar código hasta completar este diagnóstico.

## 2. Evaluación de la experiencia actual

Inspeccionar la interfaz existente y determinar qué operaciones ya pueden realizarse desde el navegador.

Verificar:

- Login local.
- Creación de identidad temporal.
- Importación de identidad.
- Inicio y detención del firmante.
- Emisión de URI bunker.
- Aprobación y rechazo de conexiones.
- Aprobación y rechazo de firmas.
- Visualización del resultado final.
- Logout.

No reconstruir funcionalidades existentes.

## 3. Propuesta de cliente de demostración local

Diseñar una página de laboratorio independiente que actúe como cliente NIP-46.

Debe permitir:

- Pegar una URI bunker.
- Conectarse exclusivamente al relay local.
- Solicitar connect.
- Solicitar get_public_key.
- Solicitar ping.
- Enviar una solicitud sign_event válida.
- Enviar una solicitud sign_event inválida.
- Mostrar el resultado de cada operación.
- Mostrar claramente si la firma fue recibida y verificada.

La página debe utilizar un cliente NIP-46 real y respetar el protocolo, sin simular respuestas del firmante.

## 4. Seguridad y aislamiento

- Usar exclusivamente identidades efímeras.
- No conectar con Stacker News.
- No conectar con relays públicos.
- No utilizar la identidad privada de B4.
- No exponer secretos en pantalla, consola o logs.
- No almacenar URI bunker ni claves privadas persistentemente.
- No permitir que la página de laboratorio controle las aprobaciones del firmante.
- Mantener la aprobación humana exclusivamente en el panel del firmante.
- No debilitar políticas ni ampliar permisos.
- No incorporar esta página a la imagen de producción por defecto.

## 5. Experiencia manual

La prueba debe realizarse con dos pestañas del navegador:

Pestaña A: aplicación NIP-46 Remote Signer.

Pestaña B: cliente de demostración local.

El propietario debe poder:

1. Iniciar sesión en el firmante.
2. Crear una identidad temporal.
3. Iniciar el firmante.
4. Generar una URI de conexión.
5. Pegarla en el cliente de demostración.
6. Solicitar conexión.
7. Aprobarla desde el firmante.
8. Solicitar una firma válida.
9. Aprobarla desde el firmante.
10. Verificar que el cliente recibió una firma válida.
11. Repetir una solicitud inválida y comprobar su rechazo.
12. Verificar una aprobación fuera de plazo.

No automatizar las aprobaciones humanas.

## 6. Pruebas

Incorporar pruebas para:

- Flujo NIP-46 completo.
- Ausencia de firma automática.
- Correlación correcta de solicitudes y respuestas.
- Manejo de expiraciones.
- Reintentos y reconexiones.
- Aislamiento de sesiones.
- Rechazos por política.
- Ausencia de conexiones externas.

No aceptar como PASS una respuesta NIP-46 sin comprobar su contenido y resultado.

## 7. Entrega

Primero entregar el diagnóstico y la propuesta técnica mínima.

Indicar:

- Qué funciona actualmente desde el navegador.
- Qué necesita el cliente de laboratorio.
- Qué archivos habría que crear o modificar.
- Riesgos de seguridad.
- Pruebas necesarias.
- Tiempo y complejidad estimados.

No implementar todavía el cliente de demostración.

No hacer commit ni push.

No iniciar B6.2.

Esperar autorización expresa del propietario.

<!-- 2026-11-21T21:22:57.230Z -->
Diagnóstico primero, sin tocar código. Reúno la evidencia de lo que realmente ocurrió en la ejecución del propietario: el resumen del cliente (si se guardó), la auditoría sanitizada del firmante, las solicitudes y los registros de ambos contenedores.

> *[Llamada a herramienta: Write — C:\Users\[REDACTADO:usuario-local]\AppData\Local\Temp\claude\b79ef0bdbf584b14\35f0f3c1-13e9-47b9-832f-f6252cd2166f\scratchpad\diag_audit.py]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: PowerShell]*

<!-- 2026-11-21T21:23:40.721Z -->
La auditoría ya da una imagen muy clara. Antes de concluir, confirmo con los registros de acceso HTTP cuántas aprobaciones llegaron por la API y que mis propios scripts solo hicieron lecturas.

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: PowerShell]*

> *[Llamada a herramienta: Grep]*

<!-- 2026-11-21T21:24:59.990Z -->
Con esto el diagnóstico está completo. Dejo constancia documental (informe y registro de IA) antes de entregarle el resultado; no toco código del producto.

> *[Llamada a herramienta: Write — docs\phase-1.0B-B6.1D-diagnosis-and-proposal.md]*

> *[Llamada a herramienta: Bash]*

<!-- 2026-11-21T21:26:07.744Z -->
## Diagnóstico y propuesta (sin implementar)

El producto no firmó nada sin aprobación humana, y las «respuestas anticipadas» venían del cliente de laboratorio. No modifiqué `app/` ni ninguna otra parte del producto. El informe completo está en [docs/phase-1.0B-B6.1D-diagnosis-and-proposal.md](docs/phase-1.0B-B6.1D-diagnosis-and-proposal.md).

## 1. Firmas sin aprobación: no hubo
Revisé la auditoría del firmante (88 entradas), las solicitudes, el registro HTTP y el registro del relay. No imprimí credenciales ni claves.

- **Firmas:** hubo 3 `sign_ok`. Cada una va precedida de `pending_created` y de una decisión `approved=true, reason=humano` de esa misma solicitud, con latencias de 3,2, 3,6 y 1,6 s. Los contadores de firmas por sesión coinciden.
- **Aprobaciones:** 7 `POST …/approve` (3 `connect` y 4 `sign_event`) y 0 rechazos. Llegaron por 3 conexiones HTTP persistentes, el patrón de un navegador. Mis scripts solo hicieron lecturas, un login/logout y 3 comprobaciones CSRF; ninguna aprobación.
- **Aprobación tardía:** una aprobación humana a los 49 s fue **rechazada correctamente por la revalidación P-38**. La ventana era de 30 s; no hubo firma.
- **Identidad cargada:** empieza por `1df53cc3…`, no es la de B4 (`c5a035bf…`).

## 2. Las respuestas anticipadas: errores del cliente de laboratorio
- **Primera ejecución:** el cliente envió de inmediato la prueba tardía y esperaba que usted aprobara pasados 35 s. Usted aprobó a los 3 s, a tiempo, y obtuvo una firma válida. Él esperaba un rechazo y lo marcó FAIL.
- **Ejecuciones posteriores:** usted aprobó en 1,6 a 3,6 s, antes de que terminara su ventana de silencio de 8 s. Lo tomó por firma automática y abortó.
- **Un `connect` extra sin tarjeta:** reutilizaba una URI ya consumida. El firmante lo rechazó, como corresponde a una URI de un solo uso.

Defectos del cliente:
- La prueba «no firma sola» se basa en tiempo; debería basarse en estado.
- No correlaciona respuestas con solicitudes por id, así que podría cruzarlas.
- La prueba tardía no da ninguna indicación en pantalla.
- Es un script de terminal.

**Observación del producto, no un defecto de seguridad:** la tarjeta muestra la cuenta atrás de `APPROVAL_TTL_S`, que en la demo era 90 s. El plazo real para firmar era la ventana de 30 s menos la antigüedad de la plantilla. Usé esos valores a propósito para poder enseñar P-38, pero la interfaz no lo explica.

## 3. Qué funciona hoy desde el navegador
Todo lo del firmante: login, crear e importar identidad, iniciar y detener, emitir la URI, aprobar y rechazar conexiones y firmas, ver el resultado y cerrar sesión.

- **Verificado en la prueba manual:** login, identidades, firmante, URI y aprobaciones de conexión y de firma.
- **No probado manualmente:** el rechazo desde la interfaz. Usted tampoco llegó a cerrar sesión. Lo que vio en pantalla no consta; yo solo veo el backend.

Lo que falta no es del firmante sino una aplicación **cliente** que también se use desde el navegador.

## 4. Propuesta mínima: página de laboratorio con el cliente NDK 2.12.2 real
- **Qué es:** un servicio Node pequeño en la imagen que ya existe (`nip46-lab-node:1.0a`, la misma librería NDK que usa Stacker News). La página no hace criptografía; pide operaciones al servicio y muestra su estado.
- **Cómo se usa:** pestaña A en `127.0.0.1:8000` (firmante, donde se aprueba) y pestaña B en `127.0.0.1:18080` (cliente).
- **Qué permite:**
  - pegar la URI y conectarse solo al relay local;
  - `connect`, `get_public_key` y `ping`;
  - `sign_event` válido e inválido (origen ajeno, `kind` distinto, método, contenido, edad, reto repetido);
  - ver cada operación como enviada → esperando aprobación (con contador) → respondida;
  - ver «firma recibida y verificada» solo si el id, la firma BIP-340, la clave y el `kind` son correctos.
- **Archivos a crear:**
  - `lab/manual/client_web/{server.mjs, index.html, app.js, app.css}`;
  - `tests/e2e/test_manual_client_web.py`.
- **Archivos a modificar:**
  - `lab/manual/compose.manual.yaml`, con un servicio bajo un perfil de Compose;
  - `README.md`, con una sección corta.
- **Qué no se toca:** `app/`, el `Dockerfile` ni el `compose.yaml` del producto; la página no entra en la imagen de producción. No hay dependencias nuevas ni imagen nueva.

## 5. Riesgos de seguridad y mitigaciones
- **Aprobación desde la página B:** el servicio no tiene credenciales ni endpoint de aprobación. Aprobar solo existe en la pestaña A, protegida por cookie, CSRF y `Origin` local. Habrá una prueba que lo verifique.
- **Relays públicos o Stacker News:** el servicio rechaza cualquier relay que no sea local. Se comprobará con las conexiones TCP de los 3 contenedores y con las peticiones del navegador.
- **URI y claves:** solo en memoria, con campo oculto y claves efímeras. Nunca en logs, en `localStorage` ni en el resumen.
- **Otra página local abusando del servicio:** escucha solo en `127.0.0.1`, con token de sesión, comprobación de `Host`/`Origin` y CSP.
- **Políticas:** no cambia ninguna política ni límite del firmante.

## 6. Pruebas necesarias
Se comprueba el contenido, no solo que haya respuesta. Los clics de aprobación en estas pruebas los hace Playwright, y eso se distingue de su validación manual.

- Flujo completo con firma verificada y `outcome=signed`.
- Sin clic no hay firma, y la decisión humana aparece en la auditoría antes de `sign_ok`.
- Correlación: dos firmas simultáneas aprobadas en orden inverso, cada resultado en su solicitud.
- Expiración por tiempo y aprobación fuera de plazo.
- Reintentos: URI reutilizada, y relay reiniciado sin reconexión silenciosa.
- Aislamiento entre sesiones y clientes.
- Rechazos por política.
- Sin conexiones externas ni secretos en registros.
- Una respuesta con firma inválida no puede verse como éxito.

## 7. Tiempo y complejidad
Complejidad media: unas 350 líneas de servicio y página más unas 250 de pruebas, estimado en 0,5 a 1 jornada. El riesgo principal es la API de NDK 2.12.2 para `ping` y para los errores y tiempos de espera. Lo verificaría contra el código vendido antes de implementar.

## Decisiones que necesito de usted
1. ¿Cliente NDK real en Node (recomendado) o un cliente propio en Python? El propio probaría nuestro protocolo contra sí mismo.
2. ¿Añado «Firmar antes de N s» a la tarjeta del firmante? Sería un cambio pequeño y opcional en `app/static`.
3. ¿Ventana de 45 s y TTL de 120 s para la demo? Hace más cómodo aprobar a tiempo, y la prueba tardía exigiría esperar más de 45 s.
4. ¿Retiro `local_client.py`?

## Estado
- **La demo sigue en marcha:** el firmante en `127.0.0.1:8000` y el relay local en `127.0.0.1:17777`, con 0 conexiones TCP a direcciones públicas. Se detiene con `docker compose -p nip46-manual down`, que conserva la base de prueba, o con `down -v`, que la borra. Dígame si quiere que la detenga.
- **Git:** sigo en `4b9e51e`, sin commit ni push.
- **Hallazgo lateral:** mis pruebas Docker anteriores dejaron decenas de volúmenes anónimos de Docker. No son suyos ni tienen datos reales, y no los toqué. Propongo corregir esas pruebas con `docker rm -fv`.

Me detengo aquí y espero su autorización. Hasta entonces no implemento el cliente, no publico nada y no inicio B6.2.
