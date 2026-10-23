# =============================================================
# Catálogo de nombres propios del asistente del hogar.
#
# Responsabilidad: ser la ÚNICA fuente del mapa de pronunciacion.
# Edge TTS lee algunos nombres con reglas del ingles, asi que aqui
# se guarda su escritura fonetica en espaniol latino.
# Opera sobre frases completas, por palabra completa y sin
# distinguir mayusculas.
# =============================================================

import re

# Clave en minuscula - escritura que Edge TTS pronuncia bien
PHONETIC_MAP = {
    "angie": "Anyi",
    "michael": "Máicol",
    "isabella": "Isabela",
    "kevin": "Kebin",
    "jennifer": "Yenifer",
    "ashley": "Ashli",
    "nicole": "Nicol",
    "daniel": "Daniel",
    "natalie": "Natali",
    "brianna": "Briana",
    "helen": "Jelen",
    "sophia": "Sofia",
    "emily": "Emili",
    "joseph": "Josef",
    "jonathan": "Yonatán",
    "alisson": "Alison",
    "yaneth": "Yanet",
    "mike": "Maik",
}

_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in PHONETIC_MAP) + r")\b",
    re.IGNORECASE,
)

def normalize_for_tts(text: str) -> str:
    """Reemplaza los nombres del mapa por su escritura fonetica."""
    if not text:
        return text
    return _PATTERN.sub(lambda match: PHONETIC_MAP[match.group(0).lower()], text)