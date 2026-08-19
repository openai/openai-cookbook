import importlib.util
import pathlib
import sys
import unittest
from unittest import mock


SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "beds24_elcid_auto_replies",
    SCRIPTS / "beds24_elcid_auto_replies.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AutoReplyTests(unittest.TestCase):
    def test_extra_large_double_is_not_presented_as_extra_bed(self):
        text = MODULE.TARGET_MESSAGES[89955894]
        self.assertIn("No se trata de una cama adicional", text)

    def test_scope_is_property_channel_and_status_limited(self):
        base = {
            "id": 1,
            "propertyId": 324903,
            "channel": "booking",
            "status": "confirmed",
        }
        self.assertTrue(MODULE.booking_in_scope(base))
        self.assertFalse(MODULE.booking_in_scope({**base, "propertyId": 324882}))
        self.assertFalse(MODULE.booking_in_scope({**base, "channel": "airbnb"}))
        self.assertFalse(MODULE.booking_in_scope({**base, "status": "cancelled"}))

    def test_identical_host_message_is_idempotent(self):
        text = "Hello world!"
        messages = [{"source": "host", "message": " Hello   world! "}]
        self.assertTrue(MODULE.already_sent(messages, text))
        self.assertFalse(
            MODULE.already_sent([{"source": "guest", "message": text}], text)
        )

    @mock.patch.object(MODULE, "fetch_messages", return_value=[])
    def test_dry_run_only_proposes(self, _fetch_messages):
        booking = {
            "id": 89955894,
            "propertyId": 324903,
            "roomId": 674485,
            "channel": "booking",
            "status": "confirmed",
        }
        result = MODULE.run(
            [booking], token="token", api_base="https://example.test", execute=False
        )
        self.assertEqual(result["wouldSend"], 1)
        self.assertEqual(result["sent"], 0)

    @mock.patch.object(MODULE, "fetch_messages", return_value=[])
    def test_execute_is_structurally_refused(self, _fetch_messages):
        booking = {
            "id": 89952542,
            "propertyId": 324903,
            "roomId": 674485,
            "channel": "booking",
            "status": "confirmed",
        }
        with self.assertRaisesRegex(MODULE.AuditError, "Live Beds24 replies are retired"):
            MODULE.run(
                [booking],
                token="token",
                api_base="https://example.test",
                execute=True,
            )


if __name__ == "__main__":
    unittest.main()
