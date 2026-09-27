"""Simulacion discreta de evacuacion con capacidad, congestión y fuego."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .genetic import genetic_path
from .maps import FloorMap
from .search import a_star, breadth_first, iterative_deepening_a_star, uniform_cost

ALGORITHMS = ("BFS", "UCS", "A*", "IDA*", "GA")


@dataclass
class SimulationConfig:
    fire_period: int = 3
    spread_probability: float = 0.30
    congestion_weight: float = 2.4
    max_turns: int | None = None
    genetic_population: int = 20
    genetic_generations: int = 8


@dataclass
class Agent:
    identifier: int
    position: int | None
    route: list[int] | None = None
    route_epoch: int = -1
    active: bool = True
    evacuated: bool = False
    death_reason: str | None = None


@dataclass(frozen=True)
class SimulationResult:
    map_key: str
    algorithm: str
    seed: int
    agents: int
    evacuated: int
    survival_rate: float
    clearance_time: int | None
    deaths_fire: int
    deaths_timeout: int
    turns: int


def simulate(floor: FloorMap, algorithm: str, seed: int,
             policy_seed: int | None = None, device: str = "cpu",
             config: SimulationConfig | None = None) -> SimulationResult:
    """Ejecuta una réplica; `seed` controla el mundo y `policy_seed` la política."""
    if algorithm not in ALGORITHMS:
        raise ValueError(f"Algoritmo desconocido: {algorithm}")
    config = config or SimulationConfig()
    world_rng = np.random.default_rng(seed)
    policy_rng = np.random.default_rng(seed if policy_seed is None else policy_seed)
    fire_options = tuple(floor.index(cell) for cell in floor.fire_starts)
    fire = {fire_options[int(world_rng.integers(0, len(fire_options)))]}
    hazards = _smoke_zone(floor, fire)
    agents = _place_agents(floor, hazards, world_rng)
    epoch = 0
    deaths_fire = 0
    evacuated = 0
    last_evacuation: int | None = None
    turn_limit = config.max_turns or max(100, 4 * (floor.height + floor.width))
    passable = set(floor.passable)
    capacities = floor.capacities
    neighbors = floor.neighbors

    for turn in range(1, turn_limit + 1):
        occupancy = _occupancy(agents, floor.height * floor.width)
        cell_costs = [
            (1.0 + config.congestion_weight * (occupancy[i] / capacities[i]) ** 2)
            if capacities[i] else float("inf")
            for i in range(floor.height * floor.width)
        ]

        proposals: dict[int, int | None] = {}
        for agent in agents:
            if not agent.active or agent.position is None:
                continue
            if agent.position in hazards:
                occupancy[agent.position] -= 1
                agent.active = False
                agent.position = None
                agent.death_reason = "fuego/humo"
                deaths_fire += 1
                continue
            if (agent.route is None or not agent.route or agent.route_epoch != epoch
                    or any(step in hazards for step in agent.route)):
                route = _find_route(algorithm, agent.position, floor.exit_index, hazards,
                                    neighbors, cell_costs, floor.width, policy_rng, device,
                                    config)
                agent.route = route[1:] if route else None
                agent.route_epoch = epoch
            proposals[agent.identifier] = agent.route[0] if agent.route else None

        priority = sorted(
            (agent for agent in agents if agent.active and agent.position is not None),
            key=lambda agent: (
                len(agent.route) if agent.route else floor.height * floor.width + 1,
                policy_rng.random(),
                agent.identifier,
            ),
        )
        exit_flow = 0
        for agent in priority:
            target = proposals.get(agent.identifier)
            if target is None:
                continue
            source = agent.position
            if source is None:
                continue
            if target in hazards or target not in passable:
                agent.route = None
                continue
            if target == floor.exit_index:
                if exit_flow >= capacities[floor.exit_index]:
                    agent.route = None
                    continue
                exit_flow += 1
                occupancy[source] -= 1
                agent.active = False
                agent.evacuated = True
                agent.position = None
                agent.route = None
                evacuated += 1
                last_evacuation = turn
                continue
            if occupancy[target] >= capacities[target]:
                # Espera discreta: el agente conserva su posición y replantea.
                agent.route = None
                continue
            occupancy[source] -= 1
            occupancy[target] += 1
            agent.position = target
            if agent.route:
                agent.route.pop(0)
        if turn % config.fire_period == 0:
            new_fire = _spread_fire(floor, fire, world_rng, config.spread_probability)
            if new_fire:
                fire.update(new_fire)
                epoch += 1
                hazards = _smoke_zone(floor, fire)
                for agent in agents:
                    if agent.active and agent.position in hazards:
                        agent.active = False
                        agent.position = None
                        agent.route = None
                        agent.death_reason = "fuego/humo"
                        deaths_fire += 1

        if not any(agent.active for agent in agents):
            break

    deaths_timeout = sum(agent.active for agent in agents)
    if deaths_timeout:
        for agent in agents:
            if agent.active:
                agent.active = False
                agent.position = None
                agent.death_reason = "limite de turnos"
    survival_rate = evacuated / len(agents) if agents else 0.0
    return SimulationResult(floor.key, algorithm, seed, len(agents), evacuated,
                            survival_rate, last_evacuation, deaths_fire,
                            deaths_timeout, turn)


def _place_agents(floor: FloorMap, hazards: set[int],
                  rng: np.random.Generator) -> list[Agent]:
    candidates = np.asarray([cell for cell in floor.passable
                             if cell != floor.exit_index and cell not in hazards], dtype=int)
    rng.shuffle(candidates)
    occupancy = [0] * (floor.height * floor.width)
    positions: list[int] = []
    for cell in candidates:
        if occupancy[int(cell)] < floor.capacities[int(cell)]:
            positions.append(int(cell))
            occupancy[int(cell)] += 1
            if len(positions) == floor.agents:
                break
    if len(positions) < floor.agents:
        raise ValueError(f"No hay celdas de inicio suficientes en {floor.key}")
    return [Agent(identifier, position) for identifier, position in enumerate(positions)]


def _occupancy(agents: list[Agent], size: int) -> list[int]:
    occupancy = [0] * size
    for agent in agents:
        if agent.active and agent.position is not None:
            occupancy[agent.position] += 1
    return occupancy


def _smoke_zone(floor: FloorMap, fire: set[int]) -> set[int]:
    smoke = set(fire)
    for cell in fire:
        smoke.update(floor.neighbors[cell])
    return smoke


def _spread_fire(floor: FloorMap, fire: set[int], rng: np.random.Generator,
                 probability: float) -> set[int]:
    result: set[int] = set()
    for cell in fire:
        for neighbor in floor.neighbors[cell]:
            if neighbor not in fire and rng.random() < probability:
                result.add(neighbor)
    return result


def _find_route(algorithm: str, start: int, goal: int, blocked: set[int],
                neighbors: tuple[tuple[int, ...], ...], costs: list[float],
                width: int, rng: np.random.Generator, device: str,
                config: SimulationConfig) -> list[int] | None:
    if algorithm == "BFS":
        return breadth_first(start, goal, blocked, neighbors)
    if algorithm == "UCS":
        return uniform_cost(start, goal, blocked, neighbors, costs)
    if algorithm == "A*":
        return a_star(start, goal, blocked, neighbors, costs, width)
    if algorithm == "IDA*":
        return iterative_deepening_a_star(start, goal, blocked, neighbors, costs, width)
    return genetic_path(start, goal, blocked, neighbors, costs, rng, device,
                        population_size=config.genetic_population,
                        generations=config.genetic_generations)
