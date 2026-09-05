"""Венгерский алгоритм: задача о назначениях, минимум суммы стоимостей.

Отдельный модуль без доменных типов и без pydantic — на нём стоит всё
распределение, и ошибка здесь не видна глазами ни в одном отчёте. Проверяется
сверкой с полным перебором.

Реализация — Кун—Манкрес через кратчайшие дополняющие пути с потенциалами:
`O(строк² · столбцов)` на прямоугольной матрице, без дополнения до квадрата.
При десятке ревьюеров и сотнях работ это единицы миллисекунд.

**Стоимости целочисленные.** Потенциалы тогда остаются точными, ничьи
разрешаются по индексу, а не по погрешности, и ответ побитово одинаков на
разных машинах — ровно то, чего требует §9.5: один и тот же пул обязан давать
одно и то же распределение, иначе координатор перестанет им пользоваться.

Своя реализация вместо scipy сознательна: `linear_sum_assignment` потянул бы
scipy и numpy — около шестидесяти мегабайт в образ ради одной функции.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

INFEASIBLE: Final[int] = 10**9
"""Стоимость запрещённой пары. Алгоритм обойдёт её, если есть хоть какая-то
альтернатива; если не обойдёт — вызывающий обязан это заметить сам, сверившись
с исходной матрицей. Запрещённая пара, оставшаяся в ответе, — не назначение."""

_INF: Final[int] = 10**18


def solve(cost: Sequence[Sequence[int]]) -> list[int]:
    """Столбец для каждой строки при минимальной сумме стоимостей.

    Требует `строк <= столбцов`; дополнять матрицу фиктивными столбцами —
    забота вызывающего, потому что только он знает, чем такой столбец
    осмысленно заполнить. Возвращает список длины `строк`: индекс столбца или
    `-1`, если строке ничего не досталось.
    """
    rows = len(cost)
    cols = len(cost[0]) if rows else 0
    if not rows or not cols:
        return [-1] * rows
    if rows > cols:
        raise ValueError(f"строк больше, чем столбцов: {rows} > {cols}")

    potential_row = [0] * (rows + 1)
    potential_col = [0] * (cols + 1)
    taken_by = [0] * (cols + 1)
    came_from = [0] * (cols + 1)

    for row in range(1, rows + 1):
        taken_by[0] = row
        column = 0
        slack = [_INF] * (cols + 1)
        visited = [False] * (cols + 1)

        while True:
            visited[column] = True
            current_row = taken_by[column]
            delta = _INF
            next_column = 0
            for candidate in range(1, cols + 1):
                if visited[candidate]:
                    continue
                reduced = (
                    cost[current_row - 1][candidate - 1]
                    - potential_row[current_row]
                    - potential_col[candidate]
                )
                if reduced < slack[candidate]:
                    slack[candidate] = reduced
                    came_from[candidate] = column
                if slack[candidate] < delta:
                    delta = slack[candidate]
                    next_column = candidate
            for candidate in range(cols + 1):
                if visited[candidate]:
                    potential_row[taken_by[candidate]] += delta
                    potential_col[candidate] -= delta
                else:
                    slack[candidate] -= delta
            column = next_column
            if taken_by[column] == 0:
                break

        while column:
            previous = came_from[column]
            taken_by[column] = taken_by[previous]
            column = previous

    answer = [-1] * rows
    for candidate in range(1, cols + 1):
        if taken_by[candidate]:
            answer[taken_by[candidate] - 1] = candidate - 1
    return answer
