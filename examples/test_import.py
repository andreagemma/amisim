import amisim as sim
import time
from amisim import get_logger
from amisim.utils import read_source
from gataframe import GataFrame, Engine

app = sim.AmisimApplication()
app.init_db(db_type="sqlite", name="test.db")
app.load_settings(
    settings_path="settings.ini",
    overrides=[
        "LOGGING:LOG_LEVEL=DEBUG",
        "LOGGING:LOG_ON_FILE=True",
        "LOGGING:LOG_DIR=logs",
    ],
)
log = app.log
log.info("This is a test log message.")
log.info("Version: %s", sim.__version__)
log.info("Debug via settings_reader: %s", app.settings_reader.get("DEBUG", section="GENERAL"))
log.info("Debug via ini runtime access: %s", app.ini.get("GENERAL", "DEBUG", default=False))
log.info("Debug via ini runtime access: %s", app.ini.GENERAL.DEBUG)

with Engine.connect() as engine:
    df = read_source(
        engine=engine,
        source="/mnt/hdd/d/Documenti/Lavoro/RM1/Flagship/SW/model4italy/stuff/dati/roma/mat.parquet",
        format="parquet",
        filter="timestamp='480'",
        mapping={"o": "n", "d": "n", "od": "o", "col1": "z+n"},
        dtype={"timestamp": "float"},
    )
    log.info("DataFrame loaded:\n%s", df)
    log.info("DataFrame info:\n%s", df.info())
