import amisim as sim
import time
from amisim import get_logger
sim_app = sim.AmisimApplication()
time.sleep(1)  # wait for the logger to be configured
sim_app.init_db(db_type="sqlite", name="test.db")
time.sleep(1)  # wait for the logger to be configured
sim_app.load_settings(
    settings_path="settings.ini",
    overrides=[
        "LOGGING:LOG_LEVEL=DEBUG",
        "LOGGING:LOG_ON_FILE=True",
        "LOGGING:LOG_DIR=logs",
    ]
)
log = get_logger("amisim", 1)

log.info("This is a test log message.")
log.info("Version: %s", sim.__version__)

#TODO: Error nella stampa del log, non viene visualizzato correttamente il tempo trascorso e l'intertempo