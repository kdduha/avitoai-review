"""Примитив, на котором стоит всё распределение.

Ошибка здесь не видна глазами: план выглядит осмысленным и просто оказывается
хуже возможного. Поэтому главный тест — сверка с полным перебором.
"""

from __future__ import annotations

import random
from itertools import permutations

import pytest

from avito_reviewer.distribution.hungarian import INFEASIBLE, solve


def total(cost: list[list[int]], answer: list[int]) -> int:
    return sum(cost[row][column] for row, column in enumerate(answer) if column >= 0)


def brute_force(cost: list[list[int]]) -> int:
    rows, cols = len(cost), len(cost[0])
    return min(
        sum(cost[row][column] for row, column in enumerate(order))
        for order in permutations(range(cols), rows)
    )


def test_it_finds_the_cheapest_assignment_on_a_known_matrix():
    cost = [[4, 1, 3], [2, 0, 5], [3, 2, 2]]

    answer = solve(cost)

    assert total(cost, answer) == 5
    assert sorted(answer) == [0, 1, 2]


def test_it_matches_brute_force_on_small_random_matrices():
    """Единственная проверка, которая ловит «правдоподобно, но не оптимально»."""
    rng = random.Random(20260905)
    for _ in range(200):
        rows = rng.randint(1, 5)
        cols = rng.randint(rows, 7)
        cost = [[rng.randint(-50, 50) for _ in range(cols)] for _ in range(rows)]

        assert total(cost, solve(cost)) == brute_force(cost)


def test_a_rectangular_matrix_leaves_the_extra_columns_free():
    cost = [[5, 9, 1, 7, 3, 8], [2, 6, 4, 9, 9, 9]]

    answer = solve(cost)

    assert len(answer) == 2
    assert len(set(answer)) == 2
    assert total(cost, answer) == 3


def test_forbidden_cells_are_avoided_when_anything_else_fits():
    cost = [[INFEASIBLE, 10, 20], [15, INFEASIBLE, 25], [30, 40, INFEASIBLE]]

    answer = solve(cost)

    assert total(cost, answer) < INFEASIBLE
    assert answer[0] != 0 and answer[1] != 1 and answer[2] != 2


def test_a_forbidden_pair_comes_back_marked_not_hidden():
    """Когда деваться некуда, запрет обязан остаться видимым в ответе.

    Алгоритм не имеет права молча выдать назначение, которого не может быть, —
    вызывающий отличает такую пару по исходной стоимости и уводит работу в
    нераспределённые.
    """
    cost = [[INFEASIBLE]]

    answer = solve(cost)

    assert answer == [0]
    assert cost[0][answer[0]] >= INFEASIBLE


def test_equal_costs_break_ties_by_index():
    """Ничьи разрешаются одинаково от запуска к запуску — иначе план «плавает»."""
    cost = [[7, 7, 7], [7, 7, 7]]

    assert solve(cost) == solve(cost) == solve([row[:] for row in cost])


def test_an_empty_matrix_is_not_an_error():
    assert solve([]) == []
    assert solve([[]]) == [-1]


def test_more_rows_than_columns_is_refused():
    """Дополнять матрицу — забота вызывающего: только он знает, чем."""
    with pytest.raises(ValueError):
        solve([[1, 2], [3, 4], [5, 6]])
