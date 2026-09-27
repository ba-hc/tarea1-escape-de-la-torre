"""Genera el informe academico en Markdown y PDF a partir del benchmark."""

from __future__ import annotations

import argparse
import csv
import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from .maps import MAPS

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS = ROOT / "results"
DEFAULT_REPORT = ROOT / "report"
AUTHOR = "Benjamín Alonso Henríquez Cid"
ALGORITHM_TEXT = {
    "BFS": "Búsqueda en anchura; minimiza cantidad de pasos e ignora congestión.",
    "UCS": "Costo uniforme (Dijkstra); minimiza la suma de costos de celda con congestión.",
    "A*": "Costo uniforme guiado por Manhattan, una cota inferior admisible.",
    "IDA*": "Profundización iterativa A* con la misma cota Manhattan admisible.",
    "GA": "Algoritmo genético propio: población de rutas, torneo, cruce por punto común y mutación de segmentos.",
}


def generate_report(results_dir: Path = DEFAULT_RESULTS,
                    report_dir: Path = DEFAULT_REPORT) -> tuple[Path, Path]:
    raw = _read_csv(results_dir / "raw_runs.csv")
    summary = _read_csv(results_dir / "summary.csv")
    metadata = json.loads((results_dir / "metadata.json").read_text(encoding="utf-8"))
    report_dir.mkdir(parents=True, exist_ok=True)
    md_path = report_dir / "informe.md"
    pdf_path = report_dir / "informe.pdf"
    md_path.write_text(_markdown(summary, metadata, results_dir), encoding="utf-8")
    _pdf(summary, raw, metadata, results_dir, pdf_path)
    return md_path, pdf_path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _markdown(summary: list[dict], metadata: dict, results_dir: Path) -> str:
    iterations = int(metadata["iterations_per_configuration"])
    total = int(metadata["simulation_runs"])
    device = metadata["device_name"]
    lines = [
        "# Tarea 1: Escape de la Torre",
        "",
        f"**Integrante:** {AUTHOR}<br>",
        f"**Fecha:** 27 de septiembre de 2026<br>",
        f"**Experimento:** {iterations} réplicas por configuración; {total} corridas en total.<br>",
        f"**Dispositivo para el GA:** {device}",
        "",
        "## 1. Objetivo",
        "",
        "Se implementa un sistema de navegación multiagente para evacuar un piso con una sola salida, mientras el fuego se propaga y la ocupación de los pasillos penaliza el movimiento. Se comparan dos búsquedas no informadas, dos informadas y un algoritmo genético propio. La evaluación mide supervivencia y tiempo de despeje, no tiempo de ejecución.",
        "",
        "## 2. Entorno y reglas",
        "",
        "Cada réplica modela un piso independiente en una grilla bidimensional. Hay una salida por piso y los agentes solo se mueven arriba, abajo, izquierda, derecha o esperan. Las puertas estrechas y la salida tienen capacidad uno; las salas abiertas, capacidad tres. Los conflictos se resuelven dentro del turno, dando prioridad a los agentes con menos pasos restantes hasta la salida.",
        "",
        "El fuego avanza cada tres turnos. Cada vecino ortogonal transitable de una casilla en llamas se prende con probabilidad 0.30; la propagación es irreversible. Las casillas en llamas y sus vecinas transitables forman la zona de fuego/humo, que no se puede atravesar. Un agente alcanzado por esa zona es una baja.",
        "",
        "El costo de entrar a una celda es `1 + 2.4 × (ocupación / capacidad)^2`. La ocupación se actualiza durante cada turno; un movimiento que no cabe espera y fuerza una nueva planificación. Todas las acciones de movimiento cuestan al menos uno.",
        "",
        "![Los tres mapas del experimento](../results/maps.png)",
        "",
        "Los mapas se definen manualmente en el proyecto. El primero usa cuatro puertas estrechas en serie; el segundo conecta salas mediante puertas y cruces; el tercero conserva varias rutas alternativas con pocos obstáculos.",
        "",
        "## 3. Algoritmos",
        "",
    ]
    for algorithm in metadata["algorithms"]:
        lines.extend([f"### {algorithm}", "", ALGORITHM_TEXT[algorithm], ""])
        if algorithm in {"A*", "IDA*"}:
            lines.append("Manhattan es admisible porque cada movimiento ortogonal reduce la distancia al objetivo como máximo en uno y ningún paso puede costar menos de uno.")
            lines.append("")
        elif algorithm == "GA":
            lines.extend([
                "Cada individuo codifica una ruta válida como secuencia de celdas. La población inicial combina una ruta de costo uniforme con rutas perturbadas; selección por torneo y elitismo conservan candidatos buenos, el cruce une padres en una celda compartida y la mutación vuelve a buscar un segmento. La aptitud suma los costos de las celdas de destino. Usa 20 individuos y ocho generaciones por planificación. No tiene garantía de optimalidad.",
                f"La evaluación por lotes de la población se ejecutó en {device}; el resto de la simulación usa CPU.",
                "",
            ])
    lines.extend([
        "## 4. Diseño experimental y métricas",
        "",
        f"Se usaron {iterations} réplicas para cada combinación de mapa y algoritmo. La semilla base fue `{metadata['seed']}`; las comparaciones usan las mismas posiciones iniciales y la misma secuencia aleatoria de propagación del fuego dentro de cada mapa/réplica. Las semillas del comportamiento interno de cada algoritmo son independientes.",
        "",
        "La supervivencia por réplica es agentes evacuados / agentes iniciales. Se reporta el promedio y la desviación estándar entre réplicas. El tiempo de despeje es el turno en que sale el último agente de una réplica con al menos un evacuado; se reportan media, desviación estándar muestral, mínimo y máximo. Las réplicas sin evacuados no tienen tiempo de despeje definido: se cuentan aparte y no se imputan como cero.",
        "",
        f"El experimento generó {total} corridas. La duración de ejecución fue {metadata['elapsed_seconds']} segundos; esta cifra solo documenta el equipo y no es una métrica comparativa.",
        "",
        "## 5. Resultados",
        "",
        "| Mapa | Algoritmo | Supervivencia media ± DE (%) | Despeje medio ± DE (turnos) | Mín–máx | Replicas con despeje | Sin evacuados |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for row in summary:
        clearance = _format_mean_sd(row, "clearance_mean_turns", "clearance_sd_turns")
        minimum = _fmt(row.get("clearance_min_turns", ""))
        maximum = _fmt(row.get("clearance_max_turns", ""))
        lines.append(
            f"| {row['map_name']} | {row['algorithm']} | "
            f"{float(row['survival_mean_pct']):.1f} ± {float(row['survival_sd_pct']):.1f} | "
            f"{clearance} | {minimum}–{maximum} | "
            f"{row['clearance_valid_runs']}/{row['runs']} | {row['zero_evacuation_runs']} |"
        )
    lines.extend([
        "",
        "![Supervivencia](../results/survival.png)",
        "",
        "![Tiempo de despeje](../results/clearance.png)",
        "",
        "La desviación estándar de supervivencia está expresada en puntos porcentuales. Para el despeje, la estadística usa solamente réplicas con al menos un evacuado; la tabla permite ver el tamaño efectivo de esa muestra. Los datos por réplica están en `results/raw_runs.csv`, y las tablas consolidadas en `results/summary.csv`.",
        "",
        "## 6. Análisis",
        "",
    ])
    for floor in MAPS:
        subset = [row for row in summary if row["map_key"] == floor.key]
        if not subset:
            continue
        best_survival = max(subset, key=lambda row: float(row["survival_mean_pct"]))
        valid = [row for row in subset if row["clearance_mean_turns"] != ""]
        fastest = min(valid, key=lambda row: float(row["clearance_mean_turns"])) if valid else None
        sentence = (f"En **{floor.name}**, la mayor supervivencia media fue de **{best_survival['algorithm']}** "
                    f"({float(best_survival['survival_mean_pct']):.1f}%).")
        if fastest:
            sentence += (f" El menor despeje medio entre réplicas válidas fue de **{fastest['algorithm']}** "
                         f"({float(fastest['clearance_mean_turns']):.1f} turnos; "
                         f"{fastest['clearance_valid_runs']}/{fastest['runs']} réplicas válidas).")
        lines.extend([sentence, ""])
    lines.extend([
        "Las diferencias se interpretan bajo este simulador y sus parámetros; no se extrapolan a edificios reales. La desviación estándar describe la variabilidad observada y no reemplaza una prueba de significancia. La salida de capacidad uno crea un cuello de botella común en los tres mapas, mientras que la geometría y la cantidad de agentes distinguen la dificultad topológica.",
        "",
        "## 7. Conclusiones",
        "",
        "La comparación separa la influencia de la congestión en la planificación de rutas: BFS prioriza pasos, UCS y los métodos informados consideran costos de ocupación, e IDA* permite resolver el mismo objetivo con una estrategia de memoria acotada. El GA busca buenas rutas por población y mutación, pero no garantiza el óptimo. Los resultados por mapa muestran cómo capacidad, densidad y propagación del fuego cambian supervivencia y despeje.",
        "",
        "## 8. Limitaciones",
        "",
        "- El movimiento de una persona se abstrae a una celda y no modela velocidad, caídas, visibilidad ni decisiones humanas.",
        "- El fuego usa una probabilidad uniforme por vecino; no incorpora materiales, viento ni ventilación.",
        "- La zona de humo es una vecindad ortogonal estática alrededor del fuego, no una simulación física de humo.",
        "- Cada corrida considera un piso y una única salida, como acota la evaluación del enunciado.",
        "- El GA es estocástico y su calidad depende del tamaño de población, generaciones y operadores elegidos.",
        "",
        "## 9. Referencias y asistencia de IA",
        "",
        "- Dijkstra, E. W. (1959). A note on two problems in connexion with graphs. *Numerische Mathematik*, 1, 269–271. https://doi.org/10.1007/BF01386390",
        "- Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). A formal basis for the heuristic determination of minimum cost paths. *IEEE Transactions on Systems Science and Cybernetics*, 4(2), 100–107. https://doi.org/10.1109/TSSC.1968.300136",
        "- Korf, R. E. (1985). Depth-first iterative-deepening: An optimal admissible tree search. *Artificial Intelligence*, 27(1), 97–109. https://doi.org/10.1016/0004-3702(85)90084-0",
        "- Holland, J. H. (1975). *Adaptation in Natural and Artificial Systems*. University of Michigan Press.",
        "- OpenAI. (2026). ChatGPT, asistencia generativa para implementación, revisión y redacción del proyecto, 27 de septiembre de 2026.",
        "",
        "No se incorporó código copiado de repositorios externos.",
        "",
    ])
    return "\n".join(lines)


def _fmt(value: str) -> str:
    return "—" if value == "" else f"{float(value):.0f}"


def _format_mean_sd(row: dict, mean_key: str, sd_key: str) -> str:
    if row.get(mean_key, "") == "":
        return "—"
    return f"{float(row[mean_key]):.1f} ± {float(row[sd_key]):.1f}"


def _pdf(summary: list[dict], raw: list[dict], metadata: dict,
         results_dir: Path, pdf_path: Path) -> None:
    with PdfPages(pdf_path) as pdf:
        _cover_page(pdf, metadata)
        _methods_page(pdf, metadata)
        _figures_page(pdf, results_dir)
        _results_page(pdf, summary)
        _analysis_page(pdf, summary, metadata)


def _cover_page(pdf: PdfPages, metadata: dict) -> None:
    fig = plt.figure(figsize=(8.27, 11.69), facecolor="#f6f5f0")
    fig.text(0.1, 0.84, "INTELIGENCIA ARTIFICIAL · TAREA 1", fontsize=10, color="#4267ac", weight="bold")
    fig.text(0.1, 0.75, "Escape de\nla Torre", fontsize=34, weight="bold", color="#203040", linespacing=1.1)
    fig.text(0.1, 0.61, "Navegación multiagente bajo congestión y propagación del fuego", fontsize=13, color="#384858")
    fig.text(0.1, 0.49, f"Integrante: {AUTHOR}\nFecha: 27 de septiembre de 2026\n\n"
             f"{metadata['iterations_per_configuration']} réplicas por configuración  ·  "
             f"{metadata['simulation_runs']} corridas  ·  {metadata['device_name']} para el GA",
             fontsize=12, color="#203040", linespacing=1.7)
    fig.text(0.1, 0.18, "Dos búsquedas no informadas, dos informadas y un algoritmo genético propio,\n"
             "evaluados en tres mapas con una salida por piso.", fontsize=12, color="#596878", linespacing=1.5)
    fig.text(0.1, 0.07, "Asignatura: Inteligencia Artificial", fontsize=9, color="#687888")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _methods_page(pdf: PdfPages, metadata: dict) -> None:
    fig, ax = plt.subplots(figsize=(8.27, 11.69))
    ax.axis("off")
    title = "Modelo y métodos"
    ax.text(0.02, 0.97, title, fontsize=22, weight="bold", color="#203040", va="top", transform=ax.transAxes)
    blocks = [
        ("Entorno", "Tres mapas bidimensionales: puertas estrechas en serie, salas corporativas y espacio abierto. En cada réplica se ubican aleatoriamente 14, 16 o 18 agentes; todos los algoritmos comparados en el mismo mapa y réplica comparten ubicaciones iniciales y secuencia aleatoria del fuego."),
        ("Fuego, humo y congestión", "El fuego avanza cada tres turnos; cada vecino transitable se enciende con probabilidad 0.30. Fuego y vecindad ortogonal son peligrosos e intransitables. Las puertas y la salida tienen capacidad uno; las salas tienen capacidad tres. Entrar a una celda cuesta 1 + 2.4 × (ocupación / capacidad)^2."),
        ("No informada", "BFS minimiza el número de pasos sin ponderar congestión. UCS minimiza el costo acumulado de las celdas y sirve como referencia de costo óptimo en la grilla dinámica actual."),
        ("Informada", "A* e IDA* usan Manhattan. Es admisible: un paso ortogonal avanza como máximo una celda hacia la salida y cada paso tiene costo mínimo uno. IDA* repite búsquedas con umbrales crecientes de f = g + h."),
        ("Algoritmo genético", "Rutas como secuencias de celdas; inicialización con caminos de costo uniforme y variantes perturbadas; torneo, elitismo, cruce en celdas compartidas y mutación de segmentos. Población de 20 y ocho generaciones. La aptitud suma los costos del camino. No garantiza el óptimo."),
        ("Resolución de conflictos", "Cada turno, los agentes avanzan por su ruta o esperan si la siguiente celda o la salida no tiene capacidad disponible. Se prioriza a quien tiene menos pasos restantes. Una ruta bloqueada, el fuego nuevo o el humo producen replanificación."),
    ]
    y = 0.89
    for heading, body in blocks:
        ax.text(0.03, y, heading, fontsize=12, weight="bold", color="#4267ac", va="top", transform=ax.transAxes)
        y -= 0.026
        wrapped = "\n".join(textwrap.wrap(body, width=90))
        ax.text(0.03, y, wrapped, fontsize=9.1, color="#293847", va="top", linespacing=1.35, transform=ax.transAxes)
        y -= 0.028 * (len(wrapped.splitlines()) + 1)
    ax.text(0.03, 0.055, f"Semilla base {metadata['seed']} · {metadata['device_name']} · Python {metadata['python']}",
            fontsize=8.5, color="#687888", transform=ax.transAxes)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _figures_page(pdf: PdfPages, results_dir: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(8.27, 11.69))
    for ax, filename, title in ((axes[0], "survival.png", "Supervivencia media ± desviación estándar"),
                                (axes[1], "clearance.png", "Despeje medio ± desviación estándar")):
        image = plt.imread(results_dir / filename)
        ax.imshow(image)
        ax.axis("off")
        ax.set_title(title, fontsize=14, weight="bold", pad=10)
    fig.suptitle("Resultados visuales", fontsize=22, weight="bold", y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _results_page(pdf: PdfPages, summary: list[dict]) -> None:
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.axis("off")
    ax.set_title("Resultados por mapa y algoritmo", fontsize=20, weight="bold", loc="left", pad=18)
    short_names = {"mapa_1": "Mapa 1 · Cuello", "mapa_2": "Mapa 2 · Laberinto",
                   "mapa_3": "Mapa 3 · Abierto"}
    cell_text = []
    for row in summary:
        surv = f"{float(row['survival_mean_pct']):.1f} ± {float(row['survival_sd_pct']):.1f}"
        if row["clearance_mean_turns"] == "":
            clearance, bounds = "—", "—"
        else:
            clearance = f"{float(row['clearance_mean_turns']):.1f} ± {float(row['clearance_sd_turns']):.1f}"
            bounds = f"{float(row['clearance_min_turns']):.0f}–{float(row['clearance_max_turns']):.0f}"
        cell_text.append([short_names[row["map_key"]], row["algorithm"], surv, clearance, bounds,
                          f"{row['clearance_valid_runs']}/{row['runs']}", row["zero_evacuation_runs"]])
    columns = ["Mapa", "Alg.", "Supervivencia %\n(media ± DE)", "Despeje turnos\n(media ± DE)",
               "Mín–máx", "N válido", "N sin\nevacuados"]
    table = ax.table(cellText=cell_text, colLabels=columns, cellLoc="center", loc="upper left",
                     colWidths=[0.22, 0.07, 0.17, 0.19, 0.11, 0.11, 0.11])
    table.auto_set_font_size(False)
    table.set_fontsize(7.8)
    table.scale(1, 1.55)
    for (row, _), cell in table.get_celld().items():
        if row == 0:
            cell.set_facecolor("#26384a")
            cell.get_text().set_color("white")
            cell.get_text().set_weight("bold")
        elif row % 2 == 0:
            cell.set_facecolor("#edf1f4")
    ax.text(0.01, 0.06, "DE = desviación estándar muestral. N válido cuenta las réplicas con al menos un evacuado; "
            "las réplicas sin evacuados se excluyen del estadístico de despeje, no del cálculo de supervivencia.",
            fontsize=8, color="#4c5a68", transform=ax.transAxes, wrap=True)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _analysis_page(pdf: PdfPages, summary: list[dict], metadata: dict) -> None:
    fig, ax = plt.subplots(figsize=(8.27, 11.69))
    ax.axis("off")
    ax.text(0.02, 0.97, "Análisis, conclusiones y referencias", fontsize=20, weight="bold",
            color="#203040", va="top", transform=ax.transAxes)
    y = 0.90
    paragraphs = []
    for floor in MAPS:
        subset = [row for row in summary if row["map_key"] == floor.key]
        if not subset:
            continue
        best = max(subset, key=lambda row: float(row["survival_mean_pct"]))
        valid = [row for row in subset if row["clearance_mean_turns"] != ""]
        fastest = min(valid, key=lambda row: float(row["clearance_mean_turns"])) if valid else None
        text = (f"En {floor.name}, {best['algorithm']} obtuvo la mayor supervivencia media "
                f"({float(best['survival_mean_pct']):.1f}%).")
        if fastest:
            text += (f" El despeje medio menor entre configuraciones con réplicas válidas fue de "
                     f"{fastest['algorithm']} ({float(fastest['clearance_mean_turns']):.1f} turnos; "
                     f"{fastest['clearance_valid_runs']}/{fastest['runs']} réplicas válidas).")
        paragraphs.append(text)
    paragraphs.extend([
        "Los resultados describen el modelo implementado y sus parámetros; no se extrapolan a edificios reales. La desviación estándar resume variabilidad, no prueba significancia estadística. El cuello de botella común de salida afecta los tres mapas, mientras que puertas, densidad y alternativas de ruta cambian el comportamiento relativo.",
        "",
        "Limitaciones: celdas discretas; movimiento sin velocidad, caídas ni percepción; propagación uniforme sin materiales o ventilación; humo representado por una vecindad ortogonal; un piso y una salida por corrida. El GA es estocástico, con 20 individuos y ocho generaciones, por lo que su calidad depende de estos parámetros.",
        "",
        "Conclusiones: BFS ofrece una referencia de menor cantidad de pasos, mientras que UCS, A* e IDA* incorporan congestión. A* e IDA* conservan heurística admisible; el GA explora rutas por población, sin garantía de optimalidad. Las métricas separan supervivencia de rapidez de despeje y mantienen visibles las réplicas que no evacuan a nadie.",
        "",
        "Referencias: Dijkstra (1959), Numerische Mathematik 1, 269–271, doi:10.1007/BF01386390; Hart, Nilsson y Raphael (1968), IEEE TSSC 4(2), 100–107, doi:10.1109/TSSC.1968.300136; Korf (1985), Artificial Intelligence 27(1), 97–109, doi:10.1016/0004-3702(85)90084-0; Holland (1975), Adaptation in Natural and Artificial Systems, University of Michigan Press.",
        "",
        "Procedencia: código implementado para esta tarea, sin código copiado de repositorios externos. ChatGPT (OpenAI, 27-09-2026) ayudó con implementación, revisión y redacción.",
        "",
        f"Corridas: {metadata['simulation_runs']} · {metadata['iterations_per_configuration']} por configuración · "
        f"semilla {metadata['seed']} · dispositivo GA: {metadata['device_name']}.",
    ])
    for paragraph in paragraphs:
        if not paragraph:
            y -= 0.018
            continue
        wrapped = "\n".join(textwrap.wrap(paragraph, width=88))
        ax.text(0.03, y, wrapped, fontsize=9.2, color="#293847", va="top", linespacing=1.35,
                transform=ax.transAxes)
        y -= 0.024 * len(wrapped.splitlines()) + 0.015
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera informe Markdown y PDF desde results/.")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    md, pdf = generate_report(args.results, args.out)
    print(f"Informe Markdown: {md.resolve()}")
    print(f"Informe PDF: {pdf.resolve()}")


if __name__ == "__main__":
    main()
