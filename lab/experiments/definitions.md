# Definiciones de los experimentos (fijadas ANTES de ejecutar)

Fuente de E1 a E6: `docs/stacker-news-compatibility.md` §3.5 (Fase 0.3). E7 y los complementos E4m, E5b y E6j se aprobaron o se
etiquetan como complemento. Los criterios de este archivo son los mismos que `lab/run_lab.py` codifica; **no se ajustan según los
resultados**. Veredictos: `PASS`, `FAIL`, `BLOCKED` (el entorno impidió ejecutar), `INCONCLUSIVE` (no se ejercitó el escenario previsto o hay un
fallo del laboratorio que impide concluir).

Cada experimento se ejecuta con el **firmante de referencia** (Node + `nostr-tools` 2.16.2, la misma biblioteca criptográfica del
navegador de Stacker News) y se **repite con el simulador Python** (NIP-04/NIP-44 propios). La regla de decisión se aplica sobre las
corridas con Python.

| Id | Definición original (Fase 0.3) | Criterio de aceptación operativo |
|---|---|---|
| E0 | (preparación) | Las pruebas `unittest` propias pasan: relay NIP-01, vectores oficiales NIP-44 válidos e inválidos, NIP-04. |
| E1 | El firmante responde **NIP-44** al `connect` NIP-04 de un `NDKNip46Signer` real contra un relay local. Éxito: `blockUntilReady()` se resuelve con la clave de identidad del firmante. | PASS si `blockUntilReady()` resuelve con la clave de **identidad** (distinta de la de transporte), el relay observó que el primer evento del cliente es **NIP-04** y el primero del firmante es **NIP-44**, y NDK registró la transición `nip04 -> nip44`. Si el escenario no se ejercitó: INCONCLUSIVE. |
| E2 | Tras E1, observar el esquema de las solicitudes siguientes y completar `sign_event` con un `kind 27235` con la forma exacta de Stacker News. Éxito: las solicitudes llegan en NIP-44; la firma devuelta verifica sin conexión sobre el `id` calculado por NDK. | PASS si se cumple E1, y además `get_public_key` y `sign_event` salen en **NIP-44** (observado en el relay), el evento firmado pasa las comprobaciones del servidor de Stacker News replicadas (id recalculado, firma Schnorr con `@noble/curves` 1.8.1, `tags[0] = ["challenge", k1]`, `pubkey` = identidad) y el firmante no registró discrepancia de `id`. |
| E3 | Descifrar en Python el primer `connect` NIP-04 real de NDK. Éxito: texto plano idéntico al esperado; sin errores de relleno. | PASS si, con el simulador Python, el SHA-256 del texto plano que NDK cifró coincide con el que Python descifró para **cada** solicitud, el primer `connect` llegó en NIP-04 y no hay errores de descifrado. |
| E4 | Modo espejo: el firmante responde **NIP-04** a todo. Éxito: el flujo completo termina igual que en E1/E2. | PASS si el flujo completo (connect, get_public_key, sign_event `27235`) termina con firma válida, **todos** los eventos del relay son NIP-04 y NDK nunca cambia de esquema. (E4m, complemento, repite con `REPLY_MODE=mirror`.) |
| E5 | Interoperabilidad NIP-44 cruzada: `nostr-tools` cifra y Python descifra, y al revés; mensajes de 1, 32, 33 y 1000 bytes y Unicode. Éxito: resultados idénticos en ambos sentidos. | PASS si todos los mensajes se descifran correctamente en ambos sentidos. Se añade 65535 bytes (límite provisional P-14). Claves de juguete fijas y públicas. (E5b, complemento no definido en la Fase 0.3: lo mismo con NIP-04.) |
| E6 | Orden y carrera: respuestas consecutivas rápidas (`ack` y luego la clave pública). Éxito: sin oscilaciones de esquema ni bloqueos. | **Operacionalización** (el texto original es breve): `ack`, `get_public_key` y **20 `sign_event` concurrentes** sin retardo. PASS si resuelve, 20/20 firmas válidas, **como máximo una** transición de esquema (`nip04 -> nip44`), sin rechazos no manejados ni errores de descifrado en el firmante. (E6j: retardo aleatorio 0-40 ms que reordena respuestas.) |
| E7 | (aprobado por el propietario) errores, mensajes inválidos y correlación. | Cada caso tiene una **predicción** tomada del análisis estático del código de NDK (más abajo). PASS si el comportamiento observado coincide con la predicción y el fallo se inyectó; FAIL si difiere (informa de una diferencia entre análisis estático y comportamiento real); INCONCLUSIVE si el fallo no llegó a inyectarse. |

## Casos de E7 y predicciones

| Caso | Inyección (en la respuesta al `connect`) | Predicción |
|---|---|---|
| `wrong_id` | Respuesta correcta con un `id` ajeno; 1,5 s después, la correcta | No resuelve con la ajena; resuelve al llegar la correcta (>= 1,4 s). |
| `error_field` | `{result:"error", error:"lab-denied"}` | `blockUntilReady()` rechaza con el texto del campo `error`. |
| `malformed_json` | Cifrado válido cuyo texto plano no es JSON; luego la correcta | NDK lo descarta con error de parseo y resuelve con la correcta. |
| `garbage` | 120 bytes aleatorios en base64; luego la correcta | NDK intenta ambos esquemas, falla, lo descarta y resuelve con la correcta. |
| `bad_mac` | NIP-44 con el último byte del MAC alterado; luego la correcta | Error `invalid MAC` en NDK; resuelve con la correcta. |
| `spoof` | `ack` firmado por **otra clave**, con el `id` correcto, y ninguna otra respuesta | **Predicción:** NDK lo acepta (correlación solo por `id`). Es un hallazgo sobre el cliente, no sobre nuestro firmante. |
| `duplicate` | La misma respuesta dos veces (dos eventos, mismo `id`) | Se procesa dos veces, resuelve una vez, sin errores. |
| `unknown_id_first` | Respuesta con `id` desconocido y luego la correcta | La desconocida se ignora; resuelve con la correcta. |
| `auth_url` | `result:"auth_url"` con una URL y, 1 s después, la final con el mismo `id` | NDK emite `authUrl` y resuelve con la final (>= 0,9 s). |
| `get_pubkey_error` | `get_public_key` responde con campo `error` | **Predicción (N7):** NDK resuelve con clave indefinida, sin rechazar. |
| `mixed` | Esquemas alternados por respuesta | NDK oscila entre esquemas (>= 2 transiciones) y resuelve. |

## Regla de decisión (Fase 0.3), sobre las corridas con Python

- E1 y E2 con Python en PASS: recomendar NIP-44 como respuesta predeterminada.
- E1 o E2 en FAIL y E4 en PASS: recomendar el modo espejo NIP-04 provisional.
- E1/E2 y E4 en FAIL: declarar bloqueo de interoperabilidad.
- Cualquier INCONCLUSIVE o BLOCKED en esas tres: no se decide (no se declara incompatibilidad por fallos del laboratorio).

Una diferencia entre la corrida de referencia y la de Python se atribuye a la criptografía propia, no a NDK, y se corrige antes de aplicar la regla.
