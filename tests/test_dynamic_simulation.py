from pathlib import Path

import pytest

import amisim as sim
from amisim.algorithms import ShortestPath, Simulation
from amisim.simulators import MicroSimulator


def test_dynamic_simulation_writes_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that dynamic simulation writes its results to temporary files."""
    test_dir = Path(__file__).parent
    monkeypatch.chdir(test_dir)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with sim.AmisimApp(
        settings_path=test_dir / "settings.ini",
        overrides_ini={"LOGGING": {"LOG_LEVEL": "DEBUG"}},
        overrides_params={
            "simulation_id": Path(__file__).stem,
            "start": "2026-10-17 07:00:00",
            "end": "2026-10-17 08:00:00",
            "params": {"output": {"location": str(output_dir)}},
        },
        params_or_path=test_dir / "params.json",
    ) as app:
        app.save_params(output_dir / "dynamic_simulation.yaml")
        app.save_settings(output_dir / "dynamic_simulation.ini")

        workspace = app.workspace
        workspace.auto_load(preload_graph=True, preload_paths=True)

        with (
            ShortestPath(use_parallel=False) as shortest_path,
            MicroSimulator(use_parallel=False) as simulator,
            Simulation(
                simulator=simulator,
                shortest_path=shortest_path,
                use_parallel=False,
            ) as loading,
        ):
            loading.init(update_last_costs=True)
            loading.run()

            agg_results_path = output_dir / "dynamic_simulation_agg_results.shp"
            paths_results_path = output_dir / "dynamic_simulation_paths_results.shp"
            stats_results_path = output_dir / "dynamic_simulation_stats_results.csv"
            trace_results_path = output_dir / "dynamic_simulation_trace_results.shp"
            signalized_results_path = output_dir / "dynamic_simulation_signalized_results.shp"

            loading.write_agg_results(
                params=agg_results_path,
                on_not_available="error",
                on_no_data="error",
                on_error="error",
            )
            loading.write_paths_results(
                params=paths_results_path,
                on_no_data="error",
                on_error="error",
            )
            loading.write_stats_results(
                params=stats_results_path,
                on_no_data="error",
                on_error="error",
            )
            loading.write_trace_results(
                params=trace_results_path,
                on_no_data="error",
                on_error="error",
            )

            signalized_results = loading.get_signalized_results()
            if signalized_results is not None and not signalized_results.empty:
                loading.write_signalized_results(
                    params=signalized_results_path,
                    on_no_data="error",
                    on_error="error",
                )

        assert loading.paths.n_paths() > 0
        assert agg_results_path.is_file()
        assert paths_results_path.is_file()
        assert stats_results_path.is_file()
        assert trace_results_path.is_file()
        if signalized_results is not None and not signalized_results.empty:
            assert signalized_results_path.is_file()
