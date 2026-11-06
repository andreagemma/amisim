from pathlib import Path

import pytest

import amisim as sim
from amisim.algorithms import AssignmentAON, ShortestPath
from amisim.simulators import StaticSimulator


def test_static_aon_writes_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that static AON assignment writes results to temporary files."""
    test_dir = Path(__file__).parent
    monkeypatch.chdir(test_dir)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with sim.AmisimApp(
        settings_path=test_dir / "settings.ini",
        overrides_ini={
            "LOGGING": {"LOG_LEVEL": "DEBUG"},
            "ASSIGNMENT": {"PRELOAD": 0, "DELTA_T": 60},
        },
        overrides_params={
            "simulation_id": Path(__file__).stem,
            "params": {"output": {"location": str(output_dir)}},
        },
        params_or_path=test_dir / "params.json",
    ) as app:
        execution = app.get_new_execution()
        app.save_params(output_dir / "static_aon.yaml")
        app.save_settings(output_dir / "static_aon.ini")

        app.workspace.auto_load()

        with (
            ShortestPath(use_parallel=False) as shortest_path,
            StaticSimulator(use_parallel=False) as simulator,
            AssignmentAON(
                execution=execution,
                simulator=simulator,
                shortest_path=shortest_path,
                use_parallel=False,
            ) as algorithm,
        ):
            algorithm.init(update_last_costs=False)
            algorithm.run()

            agg_results_path = output_dir / "static_aon_agg_results.shp"
            paths_results_path = output_dir / "static_aon_paths_results.shp"
            algorithm.write_agg_results(
                params=agg_results_path,
                on_not_available="error",
                on_no_data="error",
                on_error="error",
            )
            algorithm.write_paths_results(
                params=paths_results_path,
                on_no_data="error",
                on_error="error",
            )

        assert algorithm.paths.n_paths() > 0
        assert agg_results_path.is_file()
        assert paths_results_path.is_file()
