from pathlib import Path

from dictparser import DictParser
from parallel import Engine

from amisim import AmisimApp, ParamsParser


def test_params_parser_loads_parameters_from_path(tmp_path: Path) -> None:
    params_path = tmp_path / "params.json"
    params_path.write_text('{"simulation": {"seed": 42}}', encoding="utf-8")

    parser = ParamsParser(params_or_path=params_path)

    assert isinstance(parser, DictParser)
    assert parser.params == {"simulation": {"seed": 42}}


def test_application_load_params_associates_parser_instance(tmp_path: Path) -> None:
    params_path = tmp_path / "params.json"
    params_path.write_text('{"simulation": {"seed": 42}}', encoding="utf-8")
    app = AmisimApp()

    app.load_params(params_path)

    assert isinstance(app.parser, ParamsParser)
    assert app.parser.params == {"simulation": {"seed": 42}}


def test_application_initializes_parallel_from_ini(monkeypatch) -> None:
    initializations: list[dict[str, object]] = []
    shutdowns: list[bool] = []

    class FakeParallel:
        def __init__(self, num_cpus: int, engine: Engine | str, **kwargs: object) -> None:
            initializations.append({"num_cpus": num_cpus, "engine": engine, **kwargs})

        def shutdown(self, force: bool = False) -> None:
            shutdowns.append(force)

    monkeypatch.setattr("amisim.amisim_app.Parallel", FakeParallel)
    app = AmisimApp()

    parallel_settings = app.ini.PARALLEL
    expected_engine = Engine.parse(parallel_settings.PARALLEL_ENGINE) if parallel_settings.PARALLEL_USE else Engine.NONE
    assert initializations == []
    _ = app.parallel
    assert initializations[0]["num_cpus"] == parallel_settings.PARALLEL_NUMCPUS
    assert initializations[0]["engine"] == expected_engine
    assert "log" in initializations[0]

    app.load_settings(
        overrides={
            "PARALLEL": {
                "PARALLEL_USE": "True",
                "PARALLEL_NUMCPUS": "4",
                "PARALLEL_ENGINE": "ray",
                "PARALLEL_CLUSTER_ADDRESS": "ray://cluster",
            }
        }
    )

    app._initialize_parallel()

    assert shutdowns == [True]
    assert initializations[1]["num_cpus"] == 4
    assert initializations[1]["engine"] == Engine.RAY
    assert initializations[1]["address"] == "ray://cluster"
    assert "log" in initializations[1]
