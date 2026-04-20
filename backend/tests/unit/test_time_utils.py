import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

config_stub = ModuleType("config")
config_stub.get_settings = lambda: SimpleNamespace(clinic_timezone="America/Sao_Paulo")
sys.modules.setdefault("config", config_stub)

from time_utils import format_date_br, weekday_name_pt_br


class TimeUtilsTest(unittest.TestCase):
    def test_weekday_name_uses_correct_year(self) -> None:
        self.assertEqual(weekday_name_pt_br("2026-04-27"), "segunda-feira")
        self.assertEqual(weekday_name_pt_br("2026-04-30"), "quinta-feira")

    def test_format_date_br(self) -> None:
        self.assertEqual(format_date_br("2026-04-27"), "27/04/2026")


if __name__ == "__main__":
    unittest.main()
