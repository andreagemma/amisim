from pathlib import Path

import pytest

import amisim as sim
from amisim.algorithms import AssignmentMSA, ShortestPath
from amisim.simulators import StaticSimulator


def test_static_msa_writes_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that static MSA assignment writes results to temporary files."""
    test_dir = Path(__file__).parent
    monkeypatch.chdir(test_dir)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    max_iterations = 5

    with sim.AmisimApp(
        settings_path=test_dir / "settings.ini",
        overrides_ini={
            "LOGGING": {"LOG_LEVEL": "DEBUG"},
            "ASSIGNMENT": {"MSA_MAX_ITE": max_iterations, "PRELOAD": 0, "DELTA_T": 60},
        },
        overrides_params={
            "simulation_id": Path(__file__).stem,
            "params": {"output": {"location": str(output_dir)}},
        },
        params_or_path=test_dir / "params.json",
    ) as app:
        execution = app.get_new_execution()
        app.save_params(output_dir / "static_msa.yaml")
        app.save_settings(output_dir / "static_msa.ini")

        app.workspace.auto_load()

        with (
            ShortestPath(use_parallel=False) as shortest_path,
            StaticSimulator(use_parallel=False) as simulator,
            AssignmentMSA(
                execution=execution,
                simulator=simulator,
                shortest_path=shortest_path,
                use_parallel=False,
            ) as algorithm,
        ):
            algorithm.init(max_iterations=max_iterations, update_last_costs=False)
            algorithm.run()

            agg_results_path = output_dir / "static_msa_agg_results.shp"
            paths_results_path = output_dir / "static_msa_paths_results.shp"
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
        assert len(algorithm.iterations) == max_iterations
        assert agg_results_path.is_file()
        assert paths_results_path.is_file()
