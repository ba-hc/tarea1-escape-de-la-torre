"""Algoritmo genetico propio para minimizar longitud y congestion de una ruta."""

from __future__ import annotations

import heapq
from collections.abc import Sequence

import numpy as np


def resolve_device(requested: str = "auto") -> tuple[str, str]:
    """Devuelve (dispositivo, etiqueta). CUDA se usa solo si PyTorch lo detecta."""
    if requested not in {"auto", "cpu", "cuda"}:
        raise ValueError("device debe ser auto, cpu o cuda")
    try:
        import torch
    except ImportError:
        if requested == "cuda":
            raise RuntimeError("Se solicito CUDA; instale el extra con `pip install -e '.[cuda]'`.")
        return "cpu", "CPU (PyTorch no instalado; evaluacion NumPy)"
    available = bool(torch.cuda.is_available())
    if requested == "cuda" and not available:
        raise RuntimeError("Se solicito CUDA, pero torch.cuda.is_available() es falso.")
    if requested == "cpu" or not available:
        label = "CPU" if requested == "cpu" else "CPU (CUDA no disponible)"
        return "cpu", label
    return "cuda", torch.cuda.get_device_name(0)


def genetic_path(start: int, goal: int, blocked: set[int],
                 neighbors: Sequence[Sequence[int]], costs: Sequence[float],
                 rng: np.random.Generator, device: str = "cpu", *,
                 population_size: int = 20, generations: int = 8) -> list[int] | None:
    if start in blocked or goal in blocked:
        return None
    if start == goal:
        return [start]

    population: list[list[int]] = []
    first = _randomized_dijkstra(start, goal, blocked, neighbors, costs, rng, None)
    if first is None:
        return None
    population.append(first)
    for _ in range(population_size - 1):
        candidate = _randomized_dijkstra(start, goal, blocked, neighbors, costs, rng, 0.35)
        if candidate is not None:
            population.append(candidate)
    while len(population) < population_size:
        population.append(first.copy())

    best_route = first
    best_score = float("inf")
    for _ in range(generations):
        scores = _score_population(population, costs, device)
        ranking = np.argsort(scores)
        if scores[ranking[0]] < best_score:
            best_score = float(scores[ranking[0]])
            best_route = population[int(ranking[0])].copy()
        elite_count = max(2, population_size // 10)
        next_population = [population[int(i)].copy() for i in ranking[:elite_count]]
        while len(next_population) < population_size:
            parent1 = _tournament(population, scores, rng)
            parent2 = _tournament(population, scores, rng)
            child = _crossover(parent1, parent2, rng)
            if rng.random() < 0.35:
                child = _mutate(child, blocked, neighbors, costs, rng)
            next_population.append(child if child and child[-1] == goal else parent1.copy())
        population = next_population
    final_scores = _score_population(population, costs, device)
    final_index = int(np.argmin(final_scores))
    if final_scores[final_index] < best_score:
        best_route = population[final_index].copy()
    return best_route


def _randomized_dijkstra(start: int, goal: int, blocked: set[int],
                         neighbors: Sequence[Sequence[int]], costs: Sequence[float],
                         rng: np.random.Generator, noise: float | None) -> list[int] | None:
    distance = {start: 0.0}
    parent: dict[int, int | None] = {start: None}
    serial = 0
    frontier = [(0.0, serial, start)]
    while frontier:
        current_distance, _, current = heapq.heappop(frontier)
        if current_distance != distance.get(current):
            continue
        if current == goal:
            route: list[int] = []
            cursor: int | None = goal
            while cursor is not None:
                route.append(cursor)
                cursor = parent[cursor]
            return list(reversed(route))
        for nxt in neighbors[current]:
            if nxt in blocked:
                continue
            multiplier = 1.0 if noise is None else float(rng.uniform(1.0 - noise, 1.0 + noise))
            candidate = current_distance + costs[nxt] * multiplier
            if candidate >= distance.get(nxt, float("inf")):
                continue
            distance[nxt] = candidate
            parent[nxt] = current
            serial += 1
            heapq.heappush(frontier, (candidate, serial, nxt))
    return None


def _score_population(population: list[list[int]], costs: Sequence[float], device: str) -> np.ndarray:
    """Evalua simultaneamente los genomas; con CUDA los suma en la GPU."""
    if device == "cuda":
        import torch

        width = max(len(route) - 1 for route in population)
        matrix = np.full((len(population), width), -1, dtype=np.int64)
        for row, route in enumerate(population):
            matrix[row, :len(route) - 1] = route[1:]
        tensor = torch.as_tensor(matrix, device="cuda")
        cost_tensor = torch.as_tensor(np.asarray(costs, dtype=np.float32), device="cuda")
        mask = tensor >= 0
        values = cost_tensor[tensor.clamp_min(0)] * mask
        return values.sum(dim=1).detach().cpu().numpy()
    return np.asarray([sum(costs[cell] for cell in route[1:]) for route in population], dtype=float)


def _tournament(population: list[list[int]], scores: np.ndarray,
                rng: np.random.Generator, size: int = 3) -> list[int]:
    candidates = rng.integers(0, len(population), size=min(size, len(population)))
    winner = min((int(i) for i in candidates), key=lambda i: (scores[i], i))
    return population[winner]


def _crossover(first: list[int], second: list[int], rng: np.random.Generator) -> list[int]:
    if rng.random() >= 0.8:
        return first.copy()
    second_positions: dict[int, list[int]] = {}
    for j, cell in enumerate(second):
        second_positions.setdefault(cell, []).append(j)
    shared = [(i, j) for i, cell in enumerate(first)
              for j in second_positions.get(cell, ())]
    if not shared:
        return first.copy()
    i, j = shared[int(rng.integers(0, len(shared)))]
    return _remove_cycles(first[:i + 1] + second[j + 1:])


def _mutate(route: list[int], blocked: set[int], neighbors: Sequence[Sequence[int]],
            costs: Sequence[float], rng: np.random.Generator) -> list[int]:
    if len(route) < 4:
        return route.copy()
    left = int(rng.integers(0, len(route) - 2))
    right = int(rng.integers(left + 2, len(route)))
    replacement = _randomized_dijkstra(route[left], route[right], blocked,
                                        neighbors, costs, rng, 0.55)
    if replacement is None:
        return route.copy()
    return _remove_cycles(route[:left] + replacement + route[right + 1:])


def _remove_cycles(route: list[int]) -> list[int]:
    clean: list[int] = []
    indices: dict[int, int] = {}
    for cell in route:
        if cell in indices:
            cut = indices[cell]
            for removed in clean[cut + 1:]:
                indices.pop(removed, None)
            clean = clean[:cut + 1]
        else:
            indices[cell] = len(clean)
            clean.append(cell)
    return clean
