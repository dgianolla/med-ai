import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

pydantic_stub = ModuleType("pydantic")


class BaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


pydantic_stub.BaseModel = BaseModel
sys.modules.setdefault("pydantic", pydantic_stub)

fastapi_stub = ModuleType("fastapi")


class APIRouter:
    def post(self, *_args, **_kwargs):
        def decorator(func):
            return func
        return decorator

    def get(self, *_args, **_kwargs):
        def decorator(func):
            return func
        return decorator


class BackgroundTasks:
    def add_task(self, *_args, **_kwargs):
        return None


class HTTPException(Exception):
    pass


fastapi_stub.APIRouter = APIRouter
fastapi_stub.BackgroundTasks = BackgroundTasks
fastapi_stub.HTTPException = HTTPException
sys.modules.setdefault("fastapi", fastapi_stub)

config_stub = ModuleType("config")
config_stub.get_settings = lambda: None
sys.modules.setdefault("config", config_stub)

db_package = ModuleType("db")
db_package.__path__ = [str(BACKEND_DIR / "db")]
sys.modules.setdefault("db", db_package)

db_client_stub = ModuleType("db.client")
db_client_stub.get_supabase = None
sys.modules.setdefault("db.client", db_client_stub)

integrations_package = ModuleType("integrations")
integrations_package.__path__ = [str(BACKEND_DIR / "integrations")]
sys.modules.setdefault("integrations", integrations_package)

helena_client_stub = ModuleType("integrations.helena_client")
def _unused_send_confirmation_template_batch(*_args, **_kwargs):
    return None


helena_client_stub.send_confirmation_template_batch = _unused_send_confirmation_template_batch
sys.modules["integrations.helena_client"] = helena_client_stub

scheduling_api_stub = ModuleType("integrations.scheduling_api")
def _unused_get_agenda(*_args, **_kwargs):
    return None


scheduling_api_stub.get_agenda = _unused_get_agenda
sys.modules["integrations.scheduling_api"] = scheduling_api_stub

time_utils_stub = ModuleType("time_utils")
time_utils_stub.clinic_now = lambda: None
sys.modules["time_utils"] = time_utils_stub

schedules_spec = importlib.util.spec_from_file_location(
    "schedules_module",
    BACKEND_DIR / "routes" / "schedules.py",
)
schedules_module = importlib.util.module_from_spec(schedules_spec)
assert schedules_spec and schedules_spec.loader
sys.modules["schedules_module"] = schedules_module
schedules_spec.loader.exec_module(schedules_module)


class SchedulesConfirmationBatchTest(unittest.TestCase):
    def test_chunk_list_splits_batches_of_100(self) -> None:
        items = list(range(205))
        chunks = schedules_module._chunk_list(items, 100)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(len(chunks[0]), 100)
        self.assertEqual(len(chunks[1]), 100)
        self.assertEqual(len(chunks[2]), 5)

    def test_build_template_parameters_formats_fields(self) -> None:
        schedule = {
            "nome": "Maria",
            "data": "2026-05-03",
            "horaInicio": "08:30:00",
            "profissionalSaude": {"nome": "Dra. Silmara"},
        }

        params = schedules_module._build_template_parameters(schedule)

        self.assertEqual(
            params,
            {
                "MEDICO": "Dra. Silmara",
                "DATA": "03/05/2026",
                "HORARIO": "08:30",
            },
        )

    def test_build_session_metadata_keeps_confirmation_context(self) -> None:
        schedule = {
            "id": 123,
            "nome": "Maria",
            "data": "2026-05-03",
            "horaInicio": "08:30:00",
            "profissionalSaude": {"nome": "Dra. Silmara"},
        }

        metadata = schedules_module._build_session_metadata(schedule, "5515999999999")

        self.assertEqual(metadata["appointment_id"], "123")
        self.assertEqual(metadata["patient_phone"], "5515999999999")
        self.assertEqual(metadata["professional_name"], "Dra. Silmara")


if __name__ == "__main__":
    unittest.main()
