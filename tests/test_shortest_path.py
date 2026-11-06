from pathlib import Path

import pytest

import amisim as sim
from amisim.algorithms import ShortestPath


def test_shortest_path_writes_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that the shortest-path output is written to a temporary file."""
    test_dir = Path(__file__).parent
    monkeypatch.chdir(test_dir)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    with sim.AmisimApp(
        settings_path=test_dir / "settings.ini",
        overrides_ini={"LOGGING": {"LOG_LEVEL": "DEBUG"}},
        overrides_params={
            "simulation_id": Path(__file__).stem,
            "params": {"output": {"location": str(output_dir)}},
        },
        params_or_path=test_dir / "params.json",
    ) as app:
        exec_instance = app.get_new_execution()
        app.save_params(output_dir / "shortest_path.yaml")
        app.save_settings(output_dir / "shortest_path.ini")

        workspace = app.workspace
        workspace.auto_load()

        with ShortestPath(execution=exec_instance) as shortest_path:
            paths = shortest_path.run()
            output_path = output_dir / "shortest_path.shp"
            paths.write(graph=workspace.graph_model, params=output_path)

        assert paths.n_paths() > 0
        assert output_path.is_file()
