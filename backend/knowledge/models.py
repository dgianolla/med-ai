"""
Modelos estruturados para dados de conhecimento da clínica.

Ver backend/knowledge/pricing.json para os dados servidos por esses modelos.
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional


class Combo(BaseModel):
    """
    Combo comercial com metadados operacionais explícitos.

    Regra crítica: toda consulta em combo deve ter especialidade formal declarada.
    Combos não são tratados como agendamento único — cada etapa (coleta, consulta,
    retorno) é acompanhada separadamente pelo fluxo de combo.
    """

    id: str
    name: str
    price: float

    consultation_included: bool = False
    consultation_specialty: Optional[str] = None

    collection_included: bool = False
    collection_schedule_required: bool = False

    return_included: bool = False
    return_window_days: Optional[int] = None

    includes: list[str] = Field(default_factory=list)
    lab_exams: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_specialty_when_consultation_included(self) -> "Combo":
        if self.consultation_included and not self.consultation_specialty:
            raise ValueError(
                f"Combo '{self.id}' tem consultation_included=True mas não declara "
                f"consultation_specialty. Toda consulta em combo precisa de especialidade "
                f"formal explícita (ex: 'ginecologia', 'cardiologia', 'clinico_geral')."
            )
        return self

    @model_validator(mode="after")
    def _require_window_when_return_included(self) -> "Combo":
        if self.return_included and self.return_window_days is None:
            raise ValueError(
                f"Combo '{self.id}' tem return_included=True mas não declara "
                f"return_window_days."
            )
        return self
