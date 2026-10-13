"""Modelo falso para el modo demo y los tests: simula respuestas del LLM sin API keys."""
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage


class FakeStructuredModel(FakeMessagesListChatModel):
    """Devuelve, en orden, las respuestas que le pasamos. Soporta with_structured_output."""

    def bind_tools(self, tools, **kwargs):
        return self


def respuesta(args: dict, finish_reason: str = "stop") -> AIMessage:
    """Arma una respuesta del 'LLM' como si hubiera completado el esquema con estos datos."""
    return AIMessage(
        content="",
        tool_calls=[{"name": "ExtraccionTecnica", "args": args, "id": "fake"}],
        response_metadata={"finish_reason": finish_reason},
    )


VALIDA = {
    "tecnologias": ["FastAPI", "Redis", "PostgreSQL"],
    "nivel_de_criticidad": "alta",
    "resumen_tecnico": "API con caché en Redis y persistencia en PostgreSQL; "
                       "cuello de botella en conexiones concurrentes.",
}
SIN_TECNOLOGIAS = {**VALIDA, "tecnologias": []}
CRITICIDAD_INVALIDA = {**VALIDA, "nivel_de_criticidad": "urgentísima"}
INCOMPLETA = {"tecnologias": ["FastAPI"]}  # le faltan campos
