from abc import ABC, abstractmethod


class WhatsAppClient(ABC):
    """Interface abstrata para envio de mensagens WhatsApp.
    Implementações: WtsClient (atual), MetaClient (futuro).
    """

    @abstractmethod
    async def send_text(self, session_id: str, text: str, ref_id: str | None = None) -> str:
        """Envia mensagem de texto. Retorna o message_id."""
        ...

    @abstractmethod
    async def send_outbound_text(
        self,
        to_phone: str,
        text: str,
        from_channel_id: str,
    ) -> str:
        """Dispara mensagem outbound fria (sem sessão pré-existente). Retorna o message_id."""
        ...

    @abstractmethod
    async def send_template(
        self,
        session_id: str,
        template_id: str,
        parameters: dict | None = None,
    ) -> str:
        """Envia template de mensagem. Retorna o message_id."""
        ...

    @abstractmethod
    async def apply_tag(self, session_id: str, tag_name: str) -> None:
        """Aplica etiqueta à sessão pelo nome. Silencioso se a tag não existir."""
        ...

    @abstractmethod
    async def add_note(self, session_id: str, text: str) -> None:
        """Adiciona nota interna à sessão."""
        ...

    @abstractmethod
    async def complete_session(self, session_id: str) -> None:
        """Conclui a sessão no provedor, quando suportado."""
        ...
