# Pipeline de extracción de entidades técnicas

Recibe un texto sin procesar (un log de error o una descripción de arquitectura) y devuelve un objeto validado con las tecnologías mencionadas, el nivel de criticidad y un resumen técnico.

Pre-entrega 2 del curso de AI Engineering (Coderhouse).

## Cómo funciona

```
texto → ChatPromptTemplate → LLM.with_structured_output(ExtraccionTecnica) → validación → objeto Pydantic
                         └──────────── .with_retry() ante JSON inválido, incompleto o cortado ────────────┘
```

- **Contrato (`schemas.py`):** modelo Pydantic `ExtraccionTecnica`. `tecnologias` no puede estar vacía (se limpian espacios y duplicados), `nivel_de_criticidad` es un enum (`baja`, `media`, `alta`) y `resumen_tecnico` tiene entre 10 y 300 caracteres.
- **Prompt modular (`chain.py`):** `ChatPromptTemplate` con roles system/human; el texto entra como variable `{texto}` y las reglas de extracción como `{instrucciones}`.
- **Cadena LCEL:** `prompt | model.with_structured_output(ExtraccionTecnica, include_raw=True) | validar_salida`.
- **Validación:** `validar_salida` revisa si el modelo cortó la respuesta por límite de tokens (`finish_reason` / `stop_reason`), si el JSON no pasó la validación o si no devolvió datos estructurados.
- **Resiliencia:** `.with_retry()` reintenta hasta 3 veces con backoff exponencial solo ante errores de formato. Los errores de red y rate limit los reintenta el SDK, y si hay keys de los dos proveedores, el segundo se usa como fallback (`.with_fallbacks()`).
- **Logs:** cada paso (procesamiento, validación fallida, reintento, resultado) queda registrado con `logging`.

## Estructura

| Archivo | Contenido |
|---|---|
| `schemas.py` | Modelo Pydantic `ExtraccionTecnica` y enum `NivelCriticidad` |
| `chain.py` | Prompt, creación del modelo, cadena LCEL con reintentos y `process_text()` |
| `fakes.py` | Modelo falso para el modo demo y los tests (sin API keys) |
| `main.py` | Mini-script de prueba asíncrono |
| `tests/test_pipeline.py` | Tests con pytest |

## Cómo correrlo

Requiere Python 3.12.

```bash
py -3.12 -m venv .venv              # Windows (en Linux/Mac: python3.12 -m venv .venv)
.venv\Scripts\activate              # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env              # Linux/Mac: cp .env.example .env
```

| Comando | Qué hace |
|---|---|
| `python main.py` | Procesa un log de ejemplo con el LLM real (necesita una API key en el `.env`) |
| `python main.py --demo` | Modo offline: simula un JSON inválido, una respuesta cortada y un fallo permanente para mostrar los reintentos |
| `pytest` | Corre los tests (no necesitan API keys) |

## Variables de entorno

| Variable | Descripción |
|---|---|
| `LLM_PROVIDER` | Proveedor principal: `anthropic` u `openai` |
| `ANTHROPIC_API_KEY` | API key de Anthropic |
| `OPENAI_API_KEY` | API key de OpenAI |
| `ANTHROPIC_MODEL` | Modelo de Anthropic (ej: `claude-haiku-4-5`) |
| `OPENAI_MODEL` | Modelo de OpenAI (ej: `gpt-4o-mini`) |

Con una sola key alcanza. Si están las dos, el otro proveedor se usa como fallback.

## Ejemplo

Entrada:

```
ERROR 2026-10-14 03:12:44 - FastAPI worker timeout. Redis respondió con 'max number of clients reached'
y el pool de PostgreSQL quedó saturado. El checkout de la tienda está caído para todos los usuarios.
```

Salida:

```json
{
  "tecnologias": ["FastAPI", "Redis", "PostgreSQL"],
  "nivel_de_criticidad": "alta",
  "resumen_tecnico": "API con caché en Redis y persistencia en PostgreSQL; cuello de botella en conexiones concurrentes."
}
```

Logs del modo demo cuando el modelo devuelve una lista vacía y se recupera al segundo intento:

```
[INFO] Procesando texto (204 caracteres)
[WARNING] JSON inválido o incompleto: 1 validation error for ExtraccionTecnica → reintentando
[INFO] Validación OK
[INFO] Extracción lista: 3 tecnologías, criticidad alta
```
