from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import guest_reply_policy_runtime as runtime  # noqa: E402


class GuestReplyPolicyRuntimeTests(unittest.TestCase):
    def test_pedro_style_request_uses_confirmed_non_smoking_fact(self) -> None:
        reply = runtime.build_elcid_reply(
            "one extra-large double bed, parking and a non-smoking room",
            language="en",
            name="Pedro",
            root=ROOT / "policies",
        )
        self.assertEqual(
            reply,
            "Hello Pedro,\n\n"
            "We have noted your request for one large double bed. "
            "We have noted your parking request. "
            "All rooms at El Cid Country Club are non-smoking.\n\n"
            "Kind regards,\nEl Cid Country Club",
        )
        self.assertNotIn("subject to availability", reply.lower())
        self.assertNotIn("where possible", reply.lower())

    def test_non_smoking_only_is_stated_as_fact(self) -> None:
        reply = runtime.build_elcid_reply(
            "Do you have a non-smoking room?",
            language="en",
            name="Alex",
            root=ROOT / "policies",
        )
        self.assertIn("All rooms at El Cid Country Club are non-smoking.", reply)

    def test_spanish_request_uses_spanish_fragments(self) -> None:
        reply = runtime.build_elcid_reply(
            "cama de matrimonio, aparcamiento y habitación para no fumadores",
            language="es",
            name="Lucía",
            root=ROOT / "policies",
        )
        self.assertIn("Hemos registrado su solicitud de una cama doble grande.", reply)
        self.assertIn("Todas las habitaciones", reply)

    def test_policy_version_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory) / "policies"
            shutil.copytree(ROOT / "policies", root)
            index = json.loads(
                (root / "registry.yaml").read_text(encoding="utf-8")
            )
            index["policy_version"] = "2026.08.02.2"
            (root / "registry.yaml").write_text(
                json.dumps(index),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                runtime.GuestReplyPolicyError,
                "version mismatch",
            ):
                runtime.build_elcid_reply("non-smoking", root=root)

    def test_unsupported_text_produces_no_reply(self) -> None:
        self.assertIsNone(
            runtime.build_elcid_reply(
                "What time is breakfast?",
                root=ROOT / "policies",
            )
        )


if __name__ == "__main__":
    unittest.main()
