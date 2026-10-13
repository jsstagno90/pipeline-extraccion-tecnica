"""Mini-script de prueba.

    python main.py          → usa el LLM real (necesita API key en el .env)
    python main.py --demo   → modo offline: simula fallas para mostrar los reintentos
"""
import asyncio
import logging
import sys

from chain import ExtraccionFallidaError, construir_cadena, process_text
from fakes import (CRITICIDAD_INVALIDA, INCOMPLETA, SIN_TECNOLOGIAS, VALIDA,
                   FakeStructuredModel, respuesta)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")

TEXTO = (
    "ERROR 2026-10-14 03:12:44 - FastAPI worker timeout. Redis respondió con "
    "'max number of clients reached' y el pool de PostgreSQL quedó saturado. "
    "El checkout de la tienda está caído para todos los usuarios."
)


def mostrar(titulo: str, resultado) -> None:
    print(f"\n--- {titulo} ---")
    print(resultado.model_dump_json(indent=2))


async def modo_real():
    try:
        mostrar("Resultado", await process_text(TEXTO))
    except ExtraccionFallidaError as e:
        print(f"\nNo se pudo extraer la información: {e}")
    except RuntimeError as e:   # falta de API keys
        print(f"\n{e}\nTip: probá el modo offline con: python main.py --demo")


async def modo_demo():
    print("\n=== Caso 1: el modelo devuelve una lista vacía, se recupera al 2° intento ===")
    modelo = FakeStructuredModel(responses=[respuesta(SIN_TECNOLOGIAS), respuesta(VALIDA)])
    mostrar("Resultado", await process_text(TEXTO, construir_cadena(modelo)))

    print("\n=== Caso 2: respuesta cortada por límite de tokens, se recupera al 2° intento ===")
    modelo = FakeStructuredModel(responses=[respuesta(INCOMPLETA, finish_reason="length"), respuesta(VALIDA)])
    mostrar("Resultado", await process_text(TEXTO, construir_cadena(modelo)))

    print("\n=== Caso 3: el modelo falla siempre → error controlado, sin crash ===")
    modelo = FakeStructuredModel(responses=[respuesta(CRITICIDAD_INVALIDA)])
    try:
        await process_text(TEXTO, construir_cadena(modelo))
    except ExtraccionFallidaError:
        print("\nError controlado: no se obtuvo una salida válida tras todos los reintentos.")


if __name__ == "__main__":
    asyncio.run(modo_demo() if "--demo" in sys.argv else modo_real())
