import logging
import os

from dotenv import load_dotenv
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import ValidationError

from schemas import ExtraccionTecnica

logger = logging.getLogger("pipeline")

MAX_INTENTOS = 3


class ExtraccionFallidaError(Exception):
    """No se pudo obtener una salida válida después de todos los reintentos."""


class RespuestaIncompletaError(Exception):
    """El modelo cortó la respuesta (finish_reason / stop_reason = límite de tokens)."""


# Errores por los que vale la pena reintentar: JSON mal formado, incompleto o inválido
ERRORES_DE_FORMATO = (OutputParserException, ValidationError, RespuestaIncompletaError)


# ---------- 1. Prompt modular ----------

INSTRUCCIONES = (
    "- Listá solo tecnologías mencionadas explícitamente en el texto, sin inventar.\n"
    "- Criticidad: 'alta' si hay caída, pérdida de datos o impacto en producción; "
    "'media' si hay degradación o riesgo; 'baja' si es informativo.\n"
    "- El resumen técnico tiene que tener una o dos oraciones."
)

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "Sos un ingeniero de software senior. Extraé información técnica del texto del usuario.\n"
     "{instrucciones}"),
    ("human", "Texto a analizar:\n{texto}"),
]).partial(instrucciones=INSTRUCCIONES)


# ---------- 2. Modelo (misma lógica de configuración que el módulo 1) ----------

def crear_modelos() -> tuple[BaseChatModel, BaseChatModel | None]:
    """Crea los modelos según el .env: el principal y, si hay key del otro proveedor, uno de respaldo."""
    load_dotenv()
    proveedor = os.getenv("LLM_PROVIDER", "anthropic")
    modelos: dict[str, BaseChatModel] = {}

    if os.getenv("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic
        modelos["anthropic"] = ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"),
            max_tokens=1024,
            max_retries=2,   # reintentos de red / rate limit (los maneja el SDK)
        )
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        modelos["openai"] = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            max_tokens=1024,
            max_retries=2,
        )

    if not modelos:
        raise RuntimeError("Falta configurar ANTHROPIC_API_KEY u OPENAI_API_KEY en el .env")

    orden = [proveedor] + [p for p in modelos if p != proveedor]
    disponibles = [modelos[p] for p in orden if p in modelos]
    principal = disponibles[0]
    respaldo = disponibles[1] if len(disponibles) > 1 else None
    return principal, respaldo


# ---------- 3. Validación de la salida ----------

def _respuesta_cortada(raw) -> bool:
    """Detecta si el modelo cortó la respuesta por límite de tokens."""
    meta = getattr(raw, "response_metadata", {}) or {}
    motivo = meta.get("finish_reason") or meta.get("stop_reason")
    return motivo in ("length", "max_tokens")


def validar_salida(resultado: dict) -> ExtraccionTecnica:
    """Recibe {raw, parsed, parsing_error} y devuelve el objeto validado o lanza un error de formato."""
    if _respuesta_cortada(resultado["raw"]):
        logger.warning("Respuesta cortada por límite de tokens → reintentando")
        raise RespuestaIncompletaError("el modelo cortó la respuesta (finish_reason = límite de tokens)")

    if resultado["parsing_error"] is not None:
        logger.warning("JSON inválido o incompleto: %s → reintentando",
                       str(resultado["parsing_error"]).splitlines()[0])
        raise OutputParserException(str(resultado["parsing_error"]))

    if resultado["parsed"] is None:
        logger.warning("El modelo no devolvió datos estructurados → reintentando")
        raise OutputParserException("el modelo no devolvió una salida estructurada")

    logger.info("Validación OK")
    return resultado["parsed"]


# ---------- 4. Cadena LCEL con reintentos ----------

def construir_cadena(modelo: BaseChatModel, fallback: BaseChatModel | None = None) -> Runnable:
    def con_esquema(m: BaseChatModel) -> Runnable:
        return prompt | m.with_structured_output(ExtraccionTecnica, include_raw=True) | RunnableLambda(validar_salida)

    cadena = con_esquema(modelo)
    if fallback is not None:
        cadena = cadena.with_fallbacks([con_esquema(fallback)])

    return cadena.with_retry(
        retry_if_exception_type=ERRORES_DE_FORMATO,
        stop_after_attempt=MAX_INTENTOS,
        wait_exponential_jitter=True,
    )


# ---------- 5. Función principal ----------

async def process_text(text: str, cadena: Runnable | None = None) -> ExtraccionTecnica:
    """Procesa un texto y devuelve la extracción validada.

    Lanza ExtraccionFallidaError si después de todos los reintentos no se logra una salida válida.
    """
    cadena = cadena or construir_cadena(*crear_modelos())
    logger.info("Procesando texto (%d caracteres)", len(text))
    try:
        resultado = await cadena.ainvoke({"texto": text})
    except ERRORES_DE_FORMATO as e:
        logger.error("Sin salida válida después de %d intentos", MAX_INTENTOS)
        raise ExtraccionFallidaError(str(e)) from e
    logger.info("Extracción lista: %d tecnologías, criticidad %s",
                len(resultado.tecnologias), resultado.nivel_de_criticidad.value)
    return resultado
