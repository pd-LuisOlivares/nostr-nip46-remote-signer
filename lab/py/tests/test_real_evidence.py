"""La evidencia solo acepta eventos y campos de la lista blanca y rechaza valores con forma de secreto."""
import json
import os
import tempfile
import unittest

from lab_real.evidence import Evidence, EvidenceViolation


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "e.jsonl")
        self.ev = Evidence(self.path)

    def tearDown(self):
        self.dir.cleanup()

    def lines(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh]

    def test_allowed_event_is_written_with_timestamp(self):
        self.ev.emit("decision", kind="sign_event", approved=False, reason="humano", latency_ms=12)
        rec = self.lines()[0]
        self.assertEqual((rec["ev"], rec["approved"]), ("decision", False))
        self.assertIn("ts", rec)

    def test_violations_raise_and_write_nothing(self):
        bad = [
            ("desconocido", {}),
            ("decision", {"kind": "x", "approved": True, "reason": "r", "latency_ms": 1, "extra": 1}),
            ("request", {"method": "m", "scheme": "nip44", "client8": "c", "plaintext_sha16": "h", "secret": "x"}),
            ("request", {"method": "m", "scheme": "nip44", "client8": "a" * 64, "plaintext_sha16": "h"}),   # 64 hex
            ("policy", {"ok": True, "failed": [], "origin_seen": "bunker://" + "a" * 8, "content_ok": True,
                        "challenge_sha16": "h", "created_at_age_s": 1}),
            ("policy", {"ok": True, "failed": [], "origin_seen": "https://x/?secret=abc", "content_ok": True,
                        "challenge_sha16": "h", "created_at_age_s": 1}),
            ("error", {"where": "nsec1qqqqqq", "error_type": "x"}),
        ]
        for event, fields in bad:
            with self.subTest(event=event, campos=sorted(fields)):
                with self.assertRaises(EvidenceViolation):
                    self.ev.emit(event, **fields)
        self.assertEqual(self.lines(), [])

    def test_sixteen_hex_hashes_are_fine(self):
        self.ev.emit("policy", ok=True, failed=[], origin_seen="https://sn.lab.invalid", content_ok=True,
                     challenge_sha16="0123456789abcdef", created_at_age_s=3)
        self.assertEqual(len(self.lines()), 1)

    def test_no_path_means_no_file(self):
        Evidence(None).emit("relay_ready")


if __name__ == "__main__":
    unittest.main()
