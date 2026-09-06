import amisim as sim
import time
from amisim import get_logger

app = sim.AmisimApplication()
time.sleep(1)  # wait for the logger to be configured
app.init_db(db_type="sqlite", name="test.db")
time.sleep(1)  # wait for the logger to be configured
app.load_settings(
    settings_path="settings.ini",
    overrides=[
        "LOGGING:LOG_LEVEL=DEBUG",
        "LOGGING:LOG_ON_FILE=True",
        "LOGGING:LOG_DIR=logs",
    ],
)
log = app.log
time.sleep(1)  # wait for the logger to be configured
log.info("This is a test log message.")
time.sleep(1)  # wait for the logger to be configured
log.info("Version: %s", sim.__version__)
log.info("Debug via settings_reader: %s", app.settings_reader.get("DEBUG", section="GENERAL"))
log.info("Debug via ini runtime access: %s", app.ini.get("GENERAL", "DEBUG", default=False))
log.info("Debug via ini runtime access: %s", app.ini.GENERAL.DEBUG)
