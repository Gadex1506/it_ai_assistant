# infrastructure/metrics/latency_log.py
# =============================================================
# Registro de latencias de latencias del pipeline (STT, LLM, TTS).
#
# Responsabilidad: medir cuanto tarda cada etapa de una peticion y
# guardar una fila por peticion en un CSV, para analizar el
# rendimiento en las pruebas del build. No decide nada del pipeline.
#
# Patron Singleton (a nivel de modulo): una sola instancia de
# LatencyLogger para todo el servidor, como una libreta unica donde
# el cronometrista anota cada carrera.
#
# Privacidad: solo guarda tiempos, tamanos y conteos. Nunca el texto
# del usuario ni el de las respuestas.
#
# Se controla con variables de entorno (.env):
#   LATENCY_LOG_ENABLED = true | false   (por defecto true)
#   LATENCY_LOG_PATH    = ruta del CSV   (por defecto logs/latency_log.csv)
# =============================================================

import csv
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime

try:
    import psutil
except ImportError:  # psutil es opcional: sin el, la columna rss_mb queda vacia
    psutil = None

logger = logging.getLogger("it_ai_assistant")

LOG_ENABLED_ENV = "LATENCY_LOG_ENABLED"
LOG_PATH_ENV = "LATENCY_LOG_PATH"
DEFAULT_LOG_PATH = os.path.join("logs", "latency_log.csv")

COLUMNS = [
    "timestamp", "request_id", "status", "language", "audio_bytes",
    "stt_ms", "stt_infer_ms", "stt_chars",
    "llm_ms", "intent", "response_chars",
    "tokens_prompt", "tokens_completion", "tokens_total", "tokens_cached",
    "tts_ms", "server_total_ms", "rss_mb",
]


class PipelineTimings:
    """
    Cronometro de UNA peticion al pipeline.

    Se crea al inicio del endpoint, se va llenando etapa por etapa
    y al final el LatencyLogger lo convierte en una fila del CSV.
    """

    def __init__(self, request_id: str | None = None, language: str | None = None):
        self.request_id = request_id or uuid.uuid4().hex[:8]
        self.language = language or "auto"
        # Si nadie lo cambia, la peticion se considera fallida
        self.status = "error"
        self.audio_bytes: int | None = None
        self.stage_ms: dict[str, float] = {}
        self.stt_infer_ms: float | None = None
        self.stt_chars: int | None = None
        self.intent: str | None = None
        self.response_chars: int | None = None
        self.tokens_prompt: int | None = None
        self.tokens_completion: int | None = None
        self.tokens_total: int | None = None
        self.tokens_cached: int | None = None
        self.server_total_ms: float | None = None
        self._started = time.perf_counter()

    @contextmanager
    def stage(self, name: str):
        """
        Mide el bloque de codigo que envuelve y guarda la duracion
        bajo el nombre dado (stt, llm, tts). Mide incluso si el bloque falla.
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            self.stage_ms[name] = (time.perf_counter() - start) * 1000

    def set_usage(self, usage) -> None:
        """
        Guarda los tokens que reporta el proveedor del LLM.

        Args:
            usage: objeto o diccionario con prompt_tokens,
                completion_tokens, total_tokens y cached_tokens. Si es None no hace nada.
        """
        if usage is None:
            return

        def read(key: str):
            if isinstance(usage, dict):
                return usage.get(key)
            return getattr(usage, key, None)

        self.tokens_prompt = read("prompt_tokens")
        self.tokens_completion = read("completion_tokens")
        self.tokens_total = read("total_tokens")
        self.tokens_cached = read("cached_tokens")

    def finish(self) -> None:
        """Cierra el cronometro general de la peticion."""
        self.server_total_ms = (time.perf_counter() - self._started) * 1000

    def to_row(self) -> dict:
        """Convierte los datos medidos en una fila lista para el CSV."""
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "request_id": self.request_id,
            "status": self.status,
            "language": self.language,
            "audio_bytes": self.audio_bytes,
            "stt_ms": _round(self.stage_ms.get("stt")),
            "stt_infer_ms": _round(self.stt_infer_ms),
            "stt_chars": self.stt_chars,
            "llm_ms": _round(self.stage_ms.get("llm")),
            "intent": self.intent,
            "response_chars": self.response_chars,
            "tokens_prompt": self.tokens_prompt,
            "tokens_completion": self.tokens_completion,
            "tokens_total": self.tokens_total,
            "tokens_cached": self.tokens_cached,
            "tts_ms": _round(self.stage_ms.get("tts")),
            "server_total_ms": _round(self.server_total_ms),
            "rss_mb": _current_rss_mb(),
        }


class LatencyLogger:
    """Escribe una fila por peticion en un CSV. Nunca rompe el pipeline si falla."""

    def __init__(self, path: str, enabled: bool = True):
        self._path = path
        self._enabled = enabled
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "LatencyLogger":
        """Crea el logger leyendo LATENCY_LOG_ENABLED y LATENCY_LOG_PATH."""
        raw = os.getenv(LOG_ENABLED_ENV, "true").strip().lower()
        enabled = raw not in ("0", "false", "no", "off")
        return cls(os.getenv(LOG_PATH_ENV, DEFAULT_LOG_PATH), enabled)

    @property
    def path(self) -> str:
        return self._path

    @property
    def enabled(self) -> bool:
        return self._enabled

    def write(self, timings: PipelineTimings) -> None:
        """
        Agrega la fila de una peticion al CSV (crea archivo y encabezado
        la primera vez) y deja un resumen de una linea en la consola.

        Args:
            timings: cronometro ya finalizado de la peticion.
        """
        if not self._enabled:
            return

        row = timings.to_row()
        logger.info(
            f"[LATENCIA] id={row['request_id']} estado={row['status']} "
            f"stt={row['stt_ms']}ms llm={row['llm_ms']}ms tts={row['tts_ms']}ms "
            f"total={row['server_total_ms']}ms tokens={row['tokens_total']} cache={row['tokens_cached']}"
        )

        try:
            with self._lock:
                folder = os.path.dirname(self._path)
                if folder:
                    os.makedirs(folder, exist_ok=True)

                is_new = not os.path.exists(self._path) or os.path.getsize(self._path) == 0
                with open(self._path, "a", newline="", encoding="utf-8") as file:
                    writer = csv.DictWriter(file, fieldnames=COLUMNS)
                    if is_new:
                        writer.writeheader()
                    writer.writerow(row)
        except OSError as error:
            logger.warning(f"[LATENCIA] No se pudo escribir el log: {error}")


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _current_rss_mb() -> float | None:
    """Memoria RAM que usa el proceso del servidor, en MB (None sin psutil)."""
    if psutil is None:
        return None
    try:
        return round(psutil.Process().memory_info().rss / (1024 * 1024), 1)
    except Exception:
        return None


# Instancia unica para todo el servidor
latency_logger = LatencyLogger.from_env()