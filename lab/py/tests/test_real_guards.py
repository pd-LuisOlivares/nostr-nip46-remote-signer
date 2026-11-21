"""Guardas de codigo del laboratorio real: ninguna ruta puede contactar a Stacker News ni crear una cuenta desde estos modulos."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = sorted(list((ROOT / "lab_real").glob("*.py")) + list((ROOT / "lab_common").glob("*.py")))
HTTP_CLIENTS = re.compile(r"^\s*(import|from)\s+(requests|httpx|aiohttp|urllib\.request|http\.client|urllib3)\b", re.M)


class SourceGuards(unittest.TestCase):
    def test_modules_were_found(self):
        self.assertGreaterEqual(len(MODULES), 8)

    def test_no_http_client_libraries_are_imported(self):
        for path in MODULES:
            with self.subTest(modulo=path.name):
                self.assertIsNone(HTTP_CLIENTS.search(path.read_text(encoding="utf-8")))

    def test_stacker_news_is_never_named_in_executable_code(self):
        """El origen de Stacker News solo llega como dato de configuracion (SN_ORIGIN); el codigo nunca lo nombra ni lo contacta."""
        for path in MODULES:
            with self.subTest(modulo=path.name):
                self.assertNotIn("stacker.news", path.read_text(encoding="utf-8").lower().replace("stacker news", ""))

    def test_the_only_signing_call_with_the_identity_key_is_in_the_sign_path_after_the_observe_branch(self):
        text = (ROOT / "lab_real" / "signer.py").read_text(encoding="utf-8")
        calls = [m.start() for m in re.finditer(r"sign_event\(self\.identity_sk", text)]
        self.assertEqual(len(calls), 1)
        on_sign = text.index("async def on_sign")
        observe_branch = text.index('if self.cfg.mode == "observe":', on_sign)
        self.assertLess(on_sign, observe_branch)
        self.assertLess(observe_branch, calls[0])
        self.assertIn("return self._observe_sign(params)", text[observe_branch:observe_branch + 120])
        self.assertLess(text.index("_observe_sign(params)", observe_branch), calls[0])


if __name__ == "__main__":
    unittest.main()
