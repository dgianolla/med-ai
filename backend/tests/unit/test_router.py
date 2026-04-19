import sys
import unittest
import importlib.util
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

router_spec = importlib.util.spec_from_file_location(
    "router_module",
    BACKEND_DIR / "orchestrator" / "router.py",
)
router_module = importlib.util.module_from_spec(router_spec)
assert router_spec and router_spec.loader
router_spec.loader.exec_module(router_module)

classify_intent = router_module.classify_intent
should_handoff = router_module.should_handoff


class RouterTest(unittest.TestCase):
    def test_classify_canetas_generic_as_weight_loss(self) -> None:
        self.assertEqual(classify_intent("Gostaria de saber sobre as canetas"), "weight_loss")

    def test_should_handoff_commercial_to_weight_loss_for_canetas(self) -> None:
        self.assertEqual(
            should_handoff("commercial", "Gostaria de saber sobre as canetas"),
            "weight_loss",
        )


if __name__ == "__main__":
    unittest.main()
