import importlib.util
import pathlib
import sys
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "beds24_aumara_voucher_activate.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("voucher_activate", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class VoucherActivateTests(unittest.TestCase):
    def test_main_refreshes_token_after_property_401(self):
        property_row = {"id": MODULE.PROPERTY_ID, "discountVouchers": []}
        responses = [
            (401, {"error": "unauthorized"}),
            (200, {"token": "temporary-access-token"}),
            (200, {"data": [property_row]}),
        ]
        with (
            mock.patch.dict("os.environ", {"BEDS24_REFRESH_TOKEN": "refresh-secret"}),
            mock.patch.object(
                MODULE,
                "get_access_token",
                return_value=("limited-access-token", "access_token", "https://api.beds24.com/v2", "source", False),
            ),
            mock.patch.object(MODULE, "request_json", side_effect=responses) as request_json,
            mock.patch.object(MODULE, "APPLY", False),
        ):
            result = MODULE.main()

        self.assertEqual(result, 0)
        self.assertEqual(request_json.call_count, 3)
        self.assertEqual(request_json.call_args_list[1].kwargs["headers"], {"refreshToken": "refresh-secret"})


if __name__ == "__main__":
    unittest.main()
