"""Tres pisos de prueba con una salida cada uno."""

from __future__ import annotations

from dataclasses import dataclass

Cell = tuple[int, int]


@dataclass(frozen=True)
class FloorMap:
    key: str
    name: str
    description: str
    rows: tuple[str, ...]
    exit_cell: Cell
    fire_starts: tuple[Cell, ...]
    agents: int

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0])

    def index(self, cell: Cell) -> int:
        return cell[0] * self.width + cell[1]

    def cell(self, index: int) -> Cell:
        return divmod(index, self.width)

    @property
    def exit_index(self) -> int:
        return self.index(self.exit_cell)

    @property
    def passable(self) -> tuple[int, ...]:
        return tuple(
            self.index((r, c))
            for r, row in enumerate(self.rows)
            for c, char in enumerate(row)
            if char != "#"
        )

    @property
    def capacities(self) -> tuple[int, ...]:
        values: list[int] = []
        for row in self.rows:
            for char in row:
                values.append(0 if char == "#" else (1 if char in ":E" else 3))
        return tuple(values)

    @property
    def neighbors(self) -> tuple[tuple[int, ...], ...]:
        valid = set(self.passable)
        result: list[tuple[int, ...]] = []
        for index in range(self.height * self.width):
            r, c = self.cell(index)
            result.append(tuple(
                other
                for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
                if 0 <= nr < self.height and 0 <= nc < self.width
                for other in (self.index((nr, nc)),)
                if other in valid
            ))
        return tuple(result)


def _blank(height: int, width: int) -> list[list[str]]:
    grid = [["#" if r in (0, height - 1) or c in (0, width - 1) else "."
             for c in range(width)] for r in range(height)]
    return grid


def _freeze(grid: list[list[str]], key: str, name: str, description: str,
            exit_cell: Cell, fire_starts: tuple[Cell, ...], agents: int) -> FloorMap:
    er, ec = exit_cell
    grid[er][ec] = "E"
    return FloorMap(key, name, description, tuple("".join(row) for row in grid),
                    exit_cell, fire_starts, agents)


def _map1() -> FloorMap:
    grid = _blank(15, 23)
    # Cuatro divisiones con una puerta angosta cada una forman un cuello comun.
    for c, door_r in ((5, 3), (10, 10), (15, 7), (19, 7)):
        for r in range(1, 14):
            grid[r][c] = "#"
        grid[door_r][c] = ":"
    return _freeze(grid, "mapa_1", "Alta densidad y cuello de botella",
                   "Cuatro puertas de capacidad uno concentran el flujo hacia la salida.",
                   (7, 21), ((2, 2), (12, 2)), 14)


def _map2() -> FloorMap:
    grid = _blank(15, 25)
    # Salas corporativas comunicadas por puertas y cruces ciegos.
    for c, doors in ((7, (3, 8, 11)), (15, (4, 9)), (20, (5, 10))):
        for r in range(1, 14):
            grid[r][c] = "#"
        for r in doors:
            grid[r][c] = ":"
    for r, c0, c1, door in ((6, 1, 6, 3), (10, 8, 14, 11), (8, 16, 19, 18)):
        for c in range(c0, c1 + 1):
            grid[r][c] = "#"
        grid[r][door] = ":"
    # Obstaculos tipo mobiliario dentro de las salas.
    for r, c in ((2, 3), (3, 4), (11, 3), (2, 11), (12, 12), (3, 18), (12, 22)):
        grid[r][c] = "#"
    return _freeze(grid, "mapa_2", "Densidad media y laberinto corporativo",
                   "Salas, cruces y pasillos con varias conexiones entre sectores.",
                   (7, 23), ((2, 2), (12, 13)), 16)


def _map3() -> FloorMap:
    grid = _blank(15, 25)
    # Entorno abierto con estanterias aisladas y rutas alternativas.
    for r, c in ((2, 6), (3, 6), (4, 6), (9, 6), (10, 6),
                 (2, 13), (3, 13), (10, 13), (11, 13), (12, 13),
                 (2, 19), (3, 19), (4, 19), (10, 19), (11, 19),
                 (6, 9), (6, 10), (8, 16), (8, 17)):
        grid[r][c] = "#"
    # Una franja corta recuerda que aun los espacios abiertos tienen capacidad.
    for r, c in ((5, 11), (7, 18)):
        grid[r][c] = ":"
    return _freeze(grid, "mapa_3", "Baja densidad y dispersión abierta",
                   "Pocas obstrucciones dejan múltiples rutas hacia la única salida.",
                   (7, 23), ((1, 2), (13, 2)), 18)


MAPS: tuple[FloorMap, ...] = (_map1(), _map2(), _map3())
MAP_BY_KEY = {floor.key: floor for floor in MAPS}
