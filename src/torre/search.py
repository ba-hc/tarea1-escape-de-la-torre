"""Busquedas clasicas para rutas en una grilla con costos de congestion."""

from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Sequence


def manhattan(a: int, b: int, width: int) -> int:
    ar, ac = divmod(a, width)
    br, bc = divmod(b, width)
    return abs(ar - br) + abs(ac - bc)


def breadth_first(start: int, goal: int, blocked: set[int],
                  neighbors: Sequence[Sequence[int]]) -> list[int] | None:
    if start in blocked or goal in blocked:
        return None
    if start == goal:
        return [start]
    parent: dict[int, int | None] = {start: None}
    frontier = deque([start])
    while frontier:
        current = frontier.popleft()
        for nxt in neighbors[current]:
            if nxt in blocked or nxt in parent:
                continue
            parent[nxt] = current
            if nxt == goal:
                return _reconstruct(parent, goal)
            frontier.append(nxt)
    return None


def uniform_cost(start: int, goal: int, blocked: set[int],
                 neighbors: Sequence[Sequence[int]], costs: Sequence[float]) -> list[int] | None:
    return _best_first(start, goal, blocked, neighbors, costs, None, 0)


def a_star(start: int, goal: int, blocked: set[int],
           neighbors: Sequence[Sequence[int]], costs: Sequence[float],
           width: int) -> list[int] | None:
    return _best_first(start, goal, blocked, neighbors, costs, width, 1)


def _best_first(start: int, goal: int, blocked: set[int],
                neighbors: Sequence[Sequence[int]], costs: Sequence[float],
                width: int | None, heuristic_weight: int) -> list[int] | None:
    if start in blocked or goal in blocked:
        return None
    if start == goal:
        return [start]
    distances = {start: 0.0}
    parent: dict[int, int | None] = {start: None}
    serial = 0
    estimate = (manhattan(start, goal, width) if width is not None else 0)
    frontier: list[tuple[float, float, int, int]] = [(float(estimate), 0.0, serial, start)]
    while frontier:
        _, distance, _, current = heapq.heappop(frontier)
        if distance != distances.get(current):
            continue
        if current == goal:
            return _reconstruct(parent, goal)
        for nxt in neighbors[current]:
            if nxt in blocked:
                continue
            candidate = distance + costs[nxt]
            if candidate >= distances.get(nxt, float("inf")):
                continue
            distances[nxt] = candidate
            parent[nxt] = current
            serial += 1
            heuristic = (manhattan(nxt, goal, width) if width is not None else 0)
            heapq.heappush(frontier, (candidate + heuristic_weight * heuristic,
                                      candidate, serial, nxt))
    return None


def iterative_deepening_a_star(start: int, goal: int, blocked: set[int],
                               neighbors: Sequence[Sequence[int]], costs: Sequence[float],
                               width: int) -> list[int] | None:
    """IDA* con h Manhattan; cada movimiento cuesta al menos uno."""
    if start in blocked or goal in blocked:
        return None
    if start == goal:
        return [start]
    threshold = float(manhattan(start, goal, width))
    path = [start]
    in_path = {start}
    infinity = float("inf")

    while threshold < infinity:
        best_g = {start: 0.0}

        def visit(current: int, g: float) -> tuple[list[int] | None, float]:
            f = g + manhattan(current, goal, width)
            if f > threshold:
                return None, f
            if current == goal:
                return path.copy(), f
            next_bound = infinity
            for nxt in neighbors[current]:
                if nxt in blocked or nxt in in_path:
                    continue
                next_g = g + costs[nxt]
                if next_g >= best_g.get(nxt, infinity):
                    continue
                best_g[nxt] = next_g
                path.append(nxt)
                in_path.add(nxt)
                found, bound = visit(nxt, next_g)
                if found is not None:
                    return found, bound
                next_bound = min(next_bound, bound)
                in_path.remove(nxt)
                path.pop()
            return None, next_bound

        found, next_threshold = visit(start, 0.0)
        if found is not None:
            return found
        if next_threshold == infinity:
            return None
        threshold = next_threshold
    return None


def _reconstruct(parent: dict[int, int | None], goal: int) -> list[int]:
    route: list[int] = []
    current: int | None = goal
    while current is not None:
        route.append(current)
        current = parent[current]
    route.reverse()
    return route
