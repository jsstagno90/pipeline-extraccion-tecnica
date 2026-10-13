import asyncio
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chain import ExtraccionFallidaError, MAX_INTENTOS, construir_cadena, process_text  # noqa: E402
from fakes import (CRITICIDAD_INVALIDA, INCOMPLETA, SIN_TECNOLOGIAS, VALIDA,  # noqa: E402
                   FakeStructuredModel, respuesta)
from schemas import ExtraccionTecnica, NivelCriticidad  # noqa: E402

TEXTO = "FastAPI con Redis y PostgreSQL, caída en producción."


def correr(modelo):
    return asyncio.run(process_text(TEXTO, construir_cadena(modelo)))


# ---------- Esquema ----------

def test_esquema_valido():
    r = ExtraccionTecnica(**VALIDA)
    assert r.nivel_de_criticidad == NivelCriticidad.ALTA


def test_esquema_rechaza_lista_vacia():
    with pytest.raises(ValidationError):
        ExtraccionTecnica(**SIN_TECNOLOGIAS)


def test_esquema_rechaza_criticidad_invalida():
    with pytest.raises(ValidationError):
        ExtraccionTecnica(**CRITICIDAD_INVALIDA)


def test_esquema_limpia_duplicados_y_espacios():
    r = ExtraccionTecnica(**{**VALIDA, "tecnologias": [" Redis ", "redis", "FastAPI", ""]})
    assert r.tecnologias == ["Redis", "FastAPI"]


# ---------- Cadena ----------

def test_cadena_devuelve_objeto_validado():
    r = correr(FakeStructuredModel(responses=[respuesta(VALIDA)]))
    assert isinstance(r, ExtraccionTecnica)
    assert "Redis" in r.tecnologias


def test_reintenta_si_el_json_es_invalido():
    modelo = FakeStructuredModel(responses=[respuesta(SIN_TECNOLOGIAS), respuesta(VALIDA)])
    r = correr(modelo)
    assert r.tecnologias == ["FastAPI", "Redis", "PostgreSQL"]


def test_reintenta_si_la_respuesta_fue_cortada():
    modelo = FakeStructuredModel(responses=[respuesta(INCOMPLETA, finish_reason="length"), respuesta(VALIDA)])
    assert isinstance(correr(modelo), ExtraccionTecnica)


def test_error_controlado_despues_de_todos_los_intentos():
    llamadas = []

    class Contador(FakeStructuredModel):
        def _generate(self, *args, **kwargs):
            llamadas.append(1)
            return super()._generate(*args, **kwargs)

    with pytest.raises(ExtraccionFallidaError):
        correr(Contador(responses=[respuesta(CRITICIDAD_INVALIDA)]))
    assert len(llamadas) == MAX_INTENTOS


def test_fallback_a_otro_modelo():
    class Caido(FakeStructuredModel):
        def _generate(self, *args, **kwargs):
            raise ConnectionError("proveedor caído")

    principal = Caido(responses=[respuesta(VALIDA)])
    respaldo = FakeStructuredModel(responses=[respuesta(VALIDA)])
    r = asyncio.run(process_text(TEXTO, construir_cadena(principal, respaldo)))
    assert isinstance(r, ExtraccionTecnica)
