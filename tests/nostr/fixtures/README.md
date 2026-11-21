# Fixtures de las pruebas del núcleo Nostr

- `nostr_tools_fixtures.json`: **fotografía** generada con `lab/tools/gen_core_fixtures.mjs` (Node 22.23.5 y `nostr-tools` 2.16.2, la implementación que usa el cliente NDK de Stacker News), sin red:
  ```
  docker run --rm -i --network none nip46-lab-node:1.0a node --input-type=module < lab/tools/gen_core_fixtures.mjs > tests/nostr/fixtures/nostr_tools_fixtures.json
  ```
  Contiene serialización NIP-01 (`JSON.stringify`, incluidos todos los caracteres de control), cargas NIP-04 y NIP-44 cifradas por `nostr-tools` y claves NIP-19. Todas las claves son **de juguete** (`0x…01`, `0x…02`, `0x…03`). Los IV y nonces los elige la biblioteca, por eso el archivo se versiona y no se regenera en las pruebas.
- `bip340_official_test_vectors.csv`: **CSV oficial completo de BIP-340** (19 vectores: 9 positivos y 10 negativos; 4 con mensaje de longitud distinta de 32 bytes).
  - **Origen:** `https://raw.githubusercontent.com/bitcoin/bips/master/bip-0340/test-vectors.csv` (rama `master`; no se registró un commit concreto).
  - **Obtenido:** 2026-11-21T00:55:30Z (UTC), una única descarga por HTTPS con verificación TLS (`curl`, HTTP 200, 6892 bytes), autorizada expresamente por el propietario.
  - **SHA-256:** `34c9d1d9c3a88d524bc80778540dc43f8306ec249a7485293063c376db851c2d` (las pruebas lo comprueban).
  - **Uso:** `tests/nostr/test_keys.py::run_bip340_csv` ejecuta **todas** las filas, sin omitir ninguna (informe `filas == ejecutados`, `omitidos == 0`). Filas 0 a 14 (mensaje de 32 bytes): biblioteca y producto. Filas 15 a 18 (mensajes de 0, 1, 17 y 100 bytes): verificación con `coincurve` (que sí las admite); `coincurve` no firma mensajes que no midan 32 bytes y el producto solo firma y verifica identificadores de 32 bytes (decisión de diseño de Nostr): se comprueba ese rechazo explícito. La implementación **no se modificó** para forzar resultados.
- Vectores oficiales de NIP-44: **no se versionan** (licencia del repositorio de origen sin aclarar, P-16/P-21). Las pruebas los leen de `NIP44_VECTORS_PATH` o de `lab/vendor/vectors/nip44.vectors.json`, verifican su SHA-256 y, si el archivo falta, **se omiten con un aviso visible**. Se obtienen con `lab/tools/fetch_artifacts.py`.
