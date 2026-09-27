"""Benchmark pareado, exportacion de metricas y figuras del informe."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .genetic import resolve_device
from .maps import MAPS, MAP_BY_KEY
from .simulation import ALGORITHMS, SimulationConfig, simulate

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "results"
REPORT_DIR = PROJECT_ROOT / "report"
RAW_FIELDS = ("map_key", "map_name", "algorithm", "iteration", "seed", "agents",
              "evacuated", "survival_rate", "clearance_time", "deaths_fire",
              "deaths_timeout", "turns")


def run_benchmark(iterations: int = 200, seed: int = 20260927,
                  output_dir: Path = RESULTS_DIR, device: str = "auto",
                  selected_maps: tuple[str, ...] | None = None,
                  selected_algorithms: tuple[str, ...] | None = None) -> tuple[list[dict], dict]:
    if iterations < 1:
        raise ValueError("iterations debe ser positivo")
    selected_maps = selected_maps or tuple(floor.key for floor in MAPS)
    selected_algorithms = selected_algorithms or ALGORITHMS
    unknown_maps = set(selected_maps) - {floor.key for floor in MAPS}
    unknown_algorithms = set(selected_algorithms) - set(ALGORITHMS)
    if unknown_maps or unknown_algorithms:
        raise ValueError(f"Configuracion desconocida: mapas={unknown_maps}, algoritmos={unknown_algorithms}")
    device_name, device_label = resolve_device(device)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "raw_runs.csv"
    start_time = time.perf_counter()
    total = len(selected_maps) * len(selected_algorithms) * iterations
    complete = 0
    print(f"Benchmark: {total} corridas | {iterations} iteraciones por combinacion | {device_label}", flush=True)

    with raw_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS, lineterminator="\n")
        writer.writeheader()
        for map_index, map_key in enumerate(selected_maps):
            floor = MAP_BY_KEY[map_key]
            for iteration in range(iterations):
                world_seed = seed + map_index * 1_000_000 + iteration
                for algorithm_index, algorithm in enumerate(selected_algorithms):
                    policy_seed = world_seed + (algorithm_index + 1) * 10_000_019
                    result = simulate(floor, algorithm, world_seed, policy_seed,
                                      device_name, SimulationConfig())
                    writer.writerow({
                        "map_key": result.map_key,
                        "map_name": floor.name,
                        "algorithm": result.algorithm,
                        "iteration": iteration + 1,
                        "seed": result.seed,
                        "agents": result.agents,
                        "evacuated": result.evacuated,
                        "survival_rate": f"{result.survival_rate:.8f}",
                        "clearance_time": "" if result.clearance_time is None else result.clearance_time,
                        "deaths_fire": result.deaths_fire,
                        "deaths_timeout": result.deaths_timeout,
                        "turns": result.turns,
                    })
                    complete += 1
                handle.flush()
                if iteration == 0 or (iteration + 1) % 10 == 0 or iteration + 1 == iterations:
                    print(f"  {map_key}: replica {iteration + 1}/{iterations} "
                          f"({complete}/{total} corridas)", flush=True)

    rows = _read_csv(raw_path)
    summary = summarize(rows)
    _write_csv(output_dir / "summary.csv", summary)
    elapsed = time.perf_counter() - start_time
    metadata = {
        "project": "Escape de la Torre",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "iterations_per_configuration": iterations,
        "configurations": len(selected_maps) * len(selected_algorithms),
        "simulation_runs": total,
        "maps": list(selected_maps),
        "algorithms": list(selected_algorithms),
        "device": device_name,
        "device_name": device_label,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "elapsed_seconds": round(elapsed, 3),
        "fire_period_turns": 3,
        "fire_spread_probability_per_neighbor": 0.30,
        "smoke_model": "casillas transitables adyacentes a cada celda en llamas",
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
    plot_maps(output_dir / "maps.png")
    plot_benchmarks(summary, output_dir)
    if output_dir.resolve() == RESULTS_DIR.resolve():
        from .reporting import generate_report

        md_path, pdf_path = generate_report(output_dir, REPORT_DIR)
        print(f"Informe: {md_path} | {pdf_path}", flush=True)
    return summary, metadata


def summarize(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["map_key"], row["algorithm"])].append(row)
    summary: list[dict] = []
    for floor in MAPS:
        for algorithm in ALGORITHMS:
            values = groups.get((floor.key, algorithm), [])
            if not values:
                continue
            survival = [float(row["survival_rate"]) for row in values]
            clearances = [int(row["clearance_time"]) for row in values if row["clearance_time"] != ""]
            summary.append({
                "map_key": floor.key,
                "map_name": floor.name,
                "algorithm": algorithm,
                "runs": len(values),
                "agents_per_run": int(values[0]["agents"]),
                "evacuated_total": sum(int(row["evacuated"]) for row in values),
                "survival_mean_pct": 100.0 * statistics.mean(survival),
                "survival_sd_pct": 100.0 * statistics.stdev(survival) if len(survival) > 1 else 0.0,
                "clearance_valid_runs": len(clearances),
                "zero_evacuation_runs": sum(int(row["evacuated"]) == 0 for row in values),
                "clearance_mean_turns": statistics.mean(clearances) if clearances else "",
                "clearance_sd_turns": statistics.stdev(clearances) if len(clearances) > 1 else (0.0 if clearances else ""),
                "clearance_min_turns": min(clearances) if clearances else "",
                "clearance_max_turns": max(clearances) if clearances else "",
            })
    return summary


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def plot_maps(path: Path) -> None:
    fig, axes = plt.subplots(1, len(MAPS), figsize=(14, 5), constrained_layout=True)
    palette = {"#": 0, ".": 1, ":": 2, "E": 3}
    for axis, floor in zip(axes, MAPS):
        data = np.asarray([[palette[c] for c in row] for row in floor.rows])
        axis.imshow(data, cmap=matplotlib.colors.ListedColormap(["#26313e", "#edf0eb", "#e5a24b", "#b33d36"]),
                    vmin=0, vmax=3)
        axis.scatter([floor.exit_cell[1]], [floor.exit_cell[0]], marker="*", s=120,
                     color="#fff3ac", edgecolor="#392c1f", linewidth=0.7, zorder=3)
        for r, c in floor.fire_starts:
            axis.scatter([c], [r], marker="X", s=55, color="#e54739", edgecolor="white", zorder=4)
        axis.set_title(floor.name, fontsize=10)
        axis.set_xticks([])
        axis.set_yticks([])
    fig.suptitle("Mapas de evacuacion (X: fuentes iniciales; estrella: salida)", fontsize=12)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_benchmarks(summary: list[dict], output_dir: Path) -> None:
    if not summary:
        return
    algorithms = [name for name in ALGORITHMS if any(row["algorithm"] == name for row in summary)]
    maps = [floor for floor in MAPS if any(row["map_key"] == floor.key for row in summary)]
    colors = {"BFS": "#4267ac", "UCS": "#53a773", "A*": "#e49c38",
              "IDA*": "#8b68b5", "GA": "#d3564a"}
    fig, axes = plt.subplots(1, len(maps), figsize=(5 * len(maps), 4.8), sharey=True, constrained_layout=True)
    if len(maps) == 1:
        axes = [axes]
    for axis, floor in zip(axes, maps):
        lookup = {(row["map_key"], row["algorithm"]): row for row in summary}
        vals = [lookup[(floor.key, a)]["survival_mean_pct"] for a in algorithms]
        errors = [lookup[(floor.key, a)]["survival_sd_pct"] for a in algorithms]
        axis.bar(algorithms, vals, yerr=errors, color=[colors[a] for a in algorithms],
                 capsize=3, alpha=0.9)
        axis.set_title(floor.name, fontsize=9)
        axis.set_ylim(0, 105)
        axis.set_ylabel("Agentes evacuados (%)")
        axis.grid(axis="y", alpha=0.2)
        axis.tick_params(axis="x", rotation=25)
    fig.suptitle("Supervivencia media (barras: desviacion estandar entre replicas)")
    fig.savefig(output_dir / "survival.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, len(maps), figsize=(5 * len(maps), 4.8), sharey=True, constrained_layout=True)
    if len(maps) == 1:
        axes = [axes]
    for axis, floor in zip(axes, maps):
        lookup = {(row["map_key"], row["algorithm"]): row for row in summary}
        eligible = [a for a in algorithms if lookup[(floor.key, a)]["clearance_valid_runs"]]
        vals = [lookup[(floor.key, a)]["clearance_mean_turns"] for a in eligible]
        errors = [lookup[(floor.key, a)]["clearance_sd_turns"] for a in eligible]
        axis.bar(eligible, vals, yerr=errors, color=[colors[a] for a in eligible],
                 capsize=3, alpha=0.9)
        axis.set_title(floor.name, fontsize=9)
        axis.set_ylabel("Turnos hasta la ultima evacuacion")
        axis.grid(axis="y", alpha=0.2)
        axis.tick_params(axis="x", rotation=25)
    fig.suptitle("Tiempo de despeje (media ± desviacion estandar; solo replicas con ≥1 evacuado)")
    fig.savefig(output_dir / "clearance.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecuta el benchmark de Escape de la Torre.")
    parser.add_argument("--iterations", type=int, default=200,
                        help="replicas por combinacion mapa/algoritmo (minimo del enunciado: 80)")
    parser.add_argument("--seed", type=int, default=20260927, help="semilla base reproducible")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto",
                        help="dispositivo para evaluar la poblacion del algoritmo genetico")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR, help="directorio de resultados")
    parser.add_argument("--maps", nargs="+", choices=tuple(floor.key for floor in MAPS))
    parser.add_argument("--algorithms", nargs="+", choices=ALGORITHMS)
    args = parser.parse_args()
    summary, metadata = run_benchmark(args.iterations, args.seed, args.out, args.device,
                                      tuple(args.maps) if args.maps else None,
                                      tuple(args.algorithms) if args.algorithms else None)
    print(f"Resultados: {args.out.resolve()}")
    print(f"Resumen: {len(summary)} configuraciones | {metadata['simulation_runs']} corridas | "
          f"{metadata['elapsed_seconds']:.1f}s")


if __name__ == "__main__":
    main()
