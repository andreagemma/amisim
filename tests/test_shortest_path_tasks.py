from typing import Any, cast

from amisim.algorithms.shortest_path import get_tasks

_FakeModes = list


def test_get_tasks_yields_one_task_per_mode_timestamp_and_origin() -> None:
    tasks = list(
        get_tasks(
            nodes=[1, 2, 3],
            modes=cast(Any, _FakeModes(["car", "bus"])),
            timestamps=[0, 60],
        )
    )
    assert len(tasks) == 2 * 2 * 3
    assert all(task is not None for task in tasks)
    first = tasks[0]
    assert first == {"origin": 1, "targets": [2, 3], "mode": "car", "timestamp": 0}


def test_get_tasks_deduplicates_nodes_and_excludes_origin() -> None:
    tasks = list(
        get_tasks(
            nodes=[5, 5, 7],
            modes=cast(Any, _FakeModes(["car"])),
            timestamps=[0],
        )
    )
    assert [task["origin"] for task in tasks] == [5, 7]
    assert [task["targets"] for task in tasks] == [[7], [5]]
