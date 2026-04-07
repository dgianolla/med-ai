from abc import ABC, abstractmethod
from db.models import SessionContext, AgentResult, AgentType


class BaseAgent(ABC):
    agent_type: AgentType
    model: str = "claude-sonnet-4-6"

    @abstractmethod
    async def run(self, ctx: SessionContext) -> AgentResult:
        """Executa o agente e retorna resultado."""
        ...

    def _build_history(self, ctx: SessionContext) -> list[dict]:
        """Converte histórico de sessão para formato Anthropic messages."""
        messages = []
        for msg in ctx.conversation_history:
            role = msg.get("role", "user")
            # Anthropic aceita apenas "user" e "assistant"
            if role not in ("user", "assistant"):
                continue
            messages.append({"role": role, "content": msg["content"]})
        return messages
