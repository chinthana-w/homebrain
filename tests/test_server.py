import os
import unittest

from homebrain.modules import DEFAULT_MODULES, load_modules
from homebrain.server import build_bridge_response


class LoadModulesTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("HOMEBRAIN_MODULES_JSON", None)

    def test_defaults_are_present(self) -> None:
        modules = load_modules()
        self.assertEqual(modules, DEFAULT_MODULES)

    def test_env_override_requires_shape(self) -> None:
        os.environ["HOMEBRAIN_MODULES_JSON"] = '{"id":"bad"}'
        with self.assertRaises(ValueError):
            load_modules()


class BridgeTests(unittest.TestCase):
    def test_valid_request(self) -> None:
        payload = {"target": "llm", "message": "summarize this"}
        response = build_bridge_response(payload, DEFAULT_MODULES)
        self.assertEqual(response["status"], "accepted")
        self.assertEqual(response["target"], "llm")

    def test_unknown_target_rejected(self) -> None:
        payload = {"target": "missing", "message": "hi"}
        with self.assertRaises(ValueError):
            build_bridge_response(payload, DEFAULT_MODULES)


if __name__ == "__main__":
    unittest.main()
