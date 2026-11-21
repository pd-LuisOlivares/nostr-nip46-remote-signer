"""Mitad Python de E5/E5b. Lee por stdin los cifrados de nostr-tools, los descifra, y cifra los mismos
mensajes hacia la clave A para que nostr-tools los descifre. Claves de JUGUETE fijas y publicas."""
import json
import sys

from lab_common import nip04, nip44
from lab_common.nostr import pubkey_of

SK_A = bytes.fromhex("0" * 63 + "1")
SK_B = bytes.fromhex("0" * 63 + "2")
PK_A, PK_B = pubkey_of(SK_A), pubkey_of(SK_B)


def main() -> None:
    data = json.load(sys.stdin)
    decrypted, items = [], []
    for it in data["items"]:
        scheme, plaintext = it["scheme"], it["plaintext"]
        try:  # Python = B: descifra lo que cifro nostr-tools (A -> B)
            if scheme == "nip04":
                out = nip04.decrypt(SK_B, PK_A, it["payload"])
            else:
                out = nip44.decrypt(it["payload"], nip44.get_conversation_key(SK_B, PK_A))
            decrypted.append({"name": it["name"], "scheme": scheme, "ok": out == plaintext})
        except (nip04.Nip04Error, nip44.Nip44Error) as exc:
            decrypted.append({"name": it["name"], "scheme": scheme, "ok": False, "error": type(exc).__name__})
        # Python cifra B -> A para que nostr-tools lo descifre
        payload = nip04.encrypt(SK_B, PK_A, plaintext) if scheme == "nip04" else nip44.encrypt(plaintext, nip44.get_conversation_key(SK_B, PK_A))
        items.append({"name": it["name"], "scheme": scheme, "plaintext": plaintext, "payload": payload})
    json.dump({"origin": "python", "decrypted_nostr_tools_payloads": decrypted, "items": items}, sys.stdout)


if __name__ == "__main__":
    main()
