# tools/analyze_latency.py
# =============================================================
# Analiza los CSV de latencia del servidor (y opcionalmente el de
# Unity) y genera un resumen en Markdown para el documento.
#
# Uso:
#   python tools/analyze_latency.py logs/latency_log.csv
#   python tools/analyze_latency.py logs/latency_log.csv --unity unity_latency.csv --skip 2 --out resumen.md
#
# Solo usa la libreria estandar de Python.
# =============================================================

import argparse
import csv
import math
import platform
import statistics
import os
from collections import defaultdict

SERVER_STAGES = ["stt_ms", "llm_ms", "tts_ms", "server_total_ms"]
UNITY_STAGES = ["recording_ms", "precheck_stt_ms", "process_ms", "total_ms"]
TOKEN_COLUMNS = ["tokens_prompt", "tokens_completion", "tokens_total", "tokens_cached"]


def read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def to_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def numbers(rows: list[dict], column: str) -> list[float]:
    values = (to_float(row.get(column)) for row in rows)
    return [v for v in values if v is not None]


def stats(values: list[float]) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "n": len(ordered),
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p95": ordered[p95_index],
        "min": ordered[0],
        "max": ordered[-1],
    }


def stats_table(rows: list[dict], columns: list[str], unit: str = "ms") -> list[str]:
    lines = [
        f"| Metrica | N | Media ({unit}) | Mediana | P95 | Min | Max |",
        "|---|---|---|---|---|---|---|",
    ]
    for column in columns:
        s = stats(numbers(rows, column))
        if s is None:
            continue
        lines.append(
            f"| {column} | {s['n']} | {s['mean']:.0f} | {s['median']:.0f} | "
            f"{s['p95']:.0f} | {s['min']:.0f} | {s['max']:.0f} |"
        )
    return lines


def join_unity(server_rows: list[dict], unity_rows: list[dict]) -> list[dict]:
    """Une cada fila del servidor con la de Unity que tenga el mismo request_id."""
    unity_by_id = {row["request_id"]: row for row in unity_rows if row.get("request_id")}
    joined = []
    for row in server_rows:
        merged = dict(row)
        unity = unity_by_id.get(row.get("request_id"))
        if unity:
            for column in UNITY_STAGES:
                merged[column] = unity.get(column)
            server_total = to_float(row.get("server_total_ms"))
            process = to_float(unity.get("process_ms"))
            if server_total is not None and process is not None:
                merged["red_y_decodificacion_ms"] = str(process - server_total)
        joined.append(merged)
    return joined


def build_report(rows: list[dict], skipped: int, has_unity: bool) -> str:
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    error_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.get("status") != "ok":
            error_counts[row.get("status") or "desconocido"] += 1

    lines = [
        "# Resumen de latencia del asistente",
        "",
        f"- Equipo: {platform.system()} {platform.release()}, {platform.processor() or 'CPU no identificada'}, "
        f"{os.cpu_count()} hilos",
        f"- Python: {platform.python_version()}",
        f"- Peticiones analizadas: {len(rows)} (se descartaron las primeras {skipped} por calentamiento)",
        f"- Exitosas: {len(ok_rows)}  |  Con error: {len(rows) - len(ok_rows)}",
        "",
        "## Tiempos del servidor (peticiones exitosas)",
        "",
        *stats_table(ok_rows, SERVER_STAGES),
        "",
    ]

    if has_unity:
        lines += [
            "## Tiempos medidos en Unity (peticiones exitosas)",
            "",
            *stats_table(ok_rows, UNITY_STAGES + ["red_y_decodificacion_ms"]),
            "",
            "`total_ms` es lo que espera el usuario desde que termina de hablar hasta que Mia empieza a responder. "
            "`precheck_stt_ms` es la transcripcion previa para detectar el comando de cerrar sesion.",
            "",
        ]

    by_intent: dict[str, list[dict]] = defaultdict(list)
    for row in ok_rows:
        by_intent[row.get("intent") or "sin_intent"].append(row)
    if by_intent:
        lines += ["## Tiempo total del servidor por tipo de peticion", "",
                  "| Intent | N | Media (ms) | Mediana | P95 |", "|---|---|---|---|---|"]
        for intent, group in sorted(by_intent.items()):
            s = stats(numbers(group, "server_total_ms"))
            if s:
                lines.append(f"| {intent} | {s['n']} | {s['mean']:.0f} | {s['median']:.0f} | {s['p95']:.0f} |")
        lines.append("")

    token_stats = [(c, stats(numbers(ok_rows, c))) for c in TOKEN_COLUMNS]
    if any(s for _, s in token_stats):
        lines += ["## Tokens del LLM por peticion", "",
                  "| Tipo | Media | Mediana | P95 | Max |", "|---|---|---|---|---|"]
        for column, s in token_stats:
            if s:
                lines.append(f"| {column} | {s['mean']:.0f} | {s['median']:.0f} | {s['p95']:.0f} | {s['max']:.0f} |")
        total = sum(numbers(ok_rows, "tokens_total"))
        lines += ["", f"Total de tokens consumidos en la muestra: {total:.0f}", ""]
        # Una celda vacia en tokens_cached significa que Groq no reporto cache (no hubo acierto)
        if any(to_float(r.get("tokens_cached")) is not None for r in ok_rows):
            prompt_sum = sum(to_float(r.get("tokens_prompt")) or 0 for r in ok_rows)
            cached_sum = sum(to_float(r.get("tokens_cached")) or 0 for r in ok_rows)
            hits = sum(1 for r in ok_rows if (to_float(r.get("tokens_cached")) or 0) > 0)
            if prompt_sum:
                lines += [f"Cache de prompt: {hits} de {len(ok_rows)} peticiones tuvieron acierto; "
                          f"{cached_sum / prompt_sum * 100:.0f} % de los tokens de entrada salieron del cache.", ""]

    rss = stats(numbers(rows, "rss_mb"))
    if rss:
        lines += [f"Memoria RAM del servidor: media {rss['mean']:.0f} MB, maximo {rss['max']:.0f} MB.", ""]

    if error_counts:
        lines += ["## Errores", "", "| Estado | Cantidad |", "|---|---|"]
        for status, count in sorted(error_counts.items()):
            lines.append(f"| {status} | {count} |")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resumen de latencia del asistente")
    parser.add_argument("server_csv", help="CSV generado por el servidor (latency_log.csv)")
    parser.add_argument("--unity", help="CSV generado por Unity (unity_latency.csv)")
    parser.add_argument("--skip", type=int, default=2, help="peticiones iniciales a descartar (calentamiento)")
    parser.add_argument("--out", help="archivo Markdown de salida (opcional)")
    args = parser.parse_args()

    rows = read_csv(args.server_csv)[args.skip:]
    has_unity = bool(args.unity)
    if has_unity:
        rows = join_unity(rows, read_csv(args.unity))

    report = build_report(rows, args.skip, has_unity)
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as file:
            file.write(report)
        print(f"\nResumen guardado en {args.out}")


if __name__ == "__main__":
    main()