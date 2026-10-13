from enum import Enum

from pydantic import BaseModel, Field, field_validator


class NivelCriticidad(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


class ExtraccionTecnica(BaseModel):
    """Entidades técnicas extraídas de un texto (log, descripción de arquitectura, etc.)."""

    tecnologias: list[str] = Field(
        min_length=1,
        description="Tecnologías, lenguajes, frameworks o servicios mencionados en el texto",
    )
    nivel_de_criticidad: NivelCriticidad = Field(
        description="Qué tan urgente es el problema o la situación descrita: baja, media o alta",
    )
    resumen_tecnico: str = Field(
        min_length=10,
        max_length=300,
        description="Resumen técnico de una o dos oraciones",
    )

    @field_validator("tecnologias")
    @classmethod
    def limpiar_tecnologias(cls, valores: list[str]) -> list[str]:
        """Saca espacios, vacíos y duplicados. Si no queda ninguna, la lista es inválida."""
        limpias: list[str] = []
        for v in valores:
            v = v.strip()
            if v and v.lower() not in (x.lower() for x in limpias):
                limpias.append(v)
        if not limpias:
            raise ValueError("la lista de tecnologías no puede quedar vacía")
        return limpias
