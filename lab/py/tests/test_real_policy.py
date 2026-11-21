"""Politica restrictiva de kind 27235: cada comprobacion se prueba en positivo y en negativo."""
import json
import unittest

from lab_common import nostr
from lab_real import policy as pol

NOW = 1_800_000_000
ORIGIN = "https://sn.lab.invalid"
IDENTITY = nostr.pubkey_of(bytes.fromhex("0" * 63 + "7"))
CFG = pol.PolicyConfig(ORIGIN)
K1 = "ab" * 32


def tpl(**over):
    base = {"kind": 27235, "created_at": NOW, "content": "Stacker News Authentication",
            "tags": [["challenge", K1], ["u", ORIGIN], ["method", "GET"]]}
    base.update(over)
    return base


def run(template, seen=None, now=NOW, cfg=CFG, raw=None):
    raw = raw if raw is not None else json.dumps(template)
    checks, info = pol.evaluate(raw, IDENTITY, now, set() if seen is None else seen, cfg)
    return {c.name: c.ok for c in checks}, info


class PolicyTests(unittest.TestCase):
    def test_valid_event_passes_every_check(self):
        res, info = run(tpl())
        self.assertTrue(all(res.values()), res)
        self.assertEqual(info["origin_seen"], ORIGIN)
        self.assertEqual(len(info["challenge_sha16"]), 16)

    def test_ndk_shape_with_pubkey_and_correct_id_is_accepted(self):
        t = tpl()
        t["pubkey"] = IDENTITY
        t["id"] = nostr.event_id({"pubkey": IDENTITY, **{k: t[k] for k in ("created_at", "kind", "tags", "content")}})
        res, _ = run(t)
        self.assertTrue(all(res.values()), res)

    def test_each_violation_fails_exactly_the_expected_check(self):
        cases = {
            "origen": tpl(tags=[["challenge", K1], ["u", "https://evil.invalid"], ["method", "GET"]]),
            "estructura": tpl(tags=[["challenge", K1], ["u", ORIGIN], ["method", "GET"], ["p", "x"]]),
            "kind": tpl(kind=1),
            "created_at": tpl(created_at=NOW - 600),
            "content": tpl(content="otro texto"),
            "challenge": tpl(tags=[["challenge", "XYZ"], ["u", ORIGIN], ["method", "GET"]]),
            "metodo": tpl(tags=[["challenge", K1], ["u", ORIGIN], ["method", "POST"]]),
            "pubkey_id": {**tpl(), "pubkey": "f" * 64},
        }
        for name, template in cases.items():
            with self.subTest(violacion=name):
                res, _ = run(template)
                self.assertFalse(res[name], res)

    def test_order_matters_for_the_server_check_on_tags_0(self):
        res, _ = run(tpl(tags=[["u", ORIGIN], ["challenge", K1], ["method", "GET"]]))
        self.assertFalse(res["estructura"])

    def test_wrong_event_id_is_rejected(self):
        res, _ = run({**tpl(), "id": "0" * 64})
        self.assertFalse(res["pubkey_id"])

    def test_window_edges(self):
        self.assertTrue(run(tpl(created_at=NOW - 120))[0]["created_at"])
        self.assertFalse(run(tpl(created_at=NOW - 121))[0]["created_at"])
        self.assertTrue(run(tpl(created_at=NOW + 30))[0]["created_at"])
        self.assertFalse(run(tpl(created_at=NOW + 31))[0]["created_at"])

    def test_reused_challenge_is_rejected(self):
        seen = {pol.challenge_hash(K1)}
        self.assertFalse(run(tpl(), seen=seen)[0]["reutilizacion"])

    def test_unknown_fields_wrong_types_and_non_objects_fail_closed(self):
        for template in ({**tpl(), "extra": 1}, tpl(kind=True), tpl(created_at="1"), tpl(tags="x"), tpl(content=5)):
            with self.subTest(template=str(template)[:40]):
                res, _ = run(template)
                self.assertFalse(res["campos"])
                self.assertFalse(pol.all_ok([pol.Check(k, v) for k, v in res.items()]))
        for raw in ("[]", "no es json", "null", '"x"'):
            res, _ = run(None, raw=raw)
            self.assertFalse(res["campos"], raw)

    def test_sig_field_is_tolerated_and_ignored(self):
        res, _ = run({**tpl(), "sig": "0" * 128})
        self.assertTrue(res["campos"])

    def test_oversized_event_is_rejected(self):
        res, _ = run(tpl(content="x" * 2000))
        self.assertFalse(res["tamano"])

    def test_config_rejects_non_origin_values(self):
        for bad in ("http://stacker.news", "https://stacker.news/", "https://stacker.news/x", "stacker.news",
                    "https://u:p@stacker.news", "https://stacker.news?x=1"):
            with self.subTest(origin=bad):
                with self.assertRaises(ValueError):
                    pol.PolicyConfig(bad)
        pol.PolicyConfig("https://stacker.news")

    def test_untrusted_text_is_sanitized(self):
        self.assertEqual(pol.sanitize("a\nb\x00é"), "a?b??")
        self.assertTrue(pol.sanitize("x" * 500).endswith("..."))


if __name__ == "__main__":
    unittest.main()
