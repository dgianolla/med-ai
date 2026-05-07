import importlib.util
import sys
import unittest
from datetime import datetime
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

db_package = ModuleType("db")
db_package.__path__ = [str(BACKEND_DIR / "db")]
sys.modules.setdefault("db", db_package)

models_spec = importlib.util.spec_from_file_location(
    "db.models",
    BACKEND_DIR / "db" / "models.py",
)
models_module = importlib.util.module_from_spec(models_spec)
assert models_spec and models_spec.loader
models_spec.loader.exec_module(models_module)
sys.modules["db.models"] = models_module

parser_spec = importlib.util.spec_from_file_location(
    "message_parser_module",
    BACKEND_DIR / "integrations" / "whatsapp" / "message_parser.py",
)
parser_module = importlib.util.module_from_spec(parser_spec)
assert parser_spec and parser_spec.loader
parser_spec.loader.exec_module(parser_module)


class MetaWebhookParserTest(unittest.TestCase):
    def test_parse_meta_button_reply(self) -> None:
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "3216590801981175",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "5515996950709",
                                    "phone_number_id": "1113768821810522",
                                },
                                "contacts": [
                                    {
                                        "profile": {"name": "Daniel"},
                                        "wa_id": "5515997615435",
                                        "user_id": "BR.885794207818136",
                                    }
                                ],
                                "messages": [
                                    {
                                        "context": {
                                            "from": "5515996950709",
                                            "id": "wamid.context",
                                        },
                                        "from": "5515997615435",
                                        "from_user_id": "BR.885794207818136",
                                        "id": "wamid.reply",
                                        "timestamp": "1778196026",
                                        "type": "button",
                                        "button": {
                                            "payload": "Confirmar",
                                            "text": "Confirmar",
                                        },
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }

        incoming = parser_module.parse_webhook(payload)

        self.assertIsNotNone(incoming)
        self.assertEqual(incoming.patient_phone, "5515997615435")
        self.assertEqual(incoming.patient_name, "Daniel")
        self.assertEqual(incoming.message_type, "text")
        self.assertEqual(incoming.text, "Confirmar")
        self.assertEqual(incoming.wts_session_id, "")
        self.assertEqual(incoming.wts_message_id, "wamid.reply")
        self.assertEqual(incoming.wts_contact_id, "BR.885794207818136")
        self.assertIsInstance(incoming.received_at, datetime)


if __name__ == "__main__":
    unittest.main()
