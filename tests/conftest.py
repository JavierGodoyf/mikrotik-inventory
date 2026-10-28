import os
import tempfile
from pathlib import Path

# Debe ejecutarse antes de importar cualquier módulo de app.*: db.py crea el
# engine al importarse y config.py cachea los settings.
_TMP = Path(tempfile.mkdtemp(prefix="mtik-tests-"))

os.environ["MTIK_DB_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["MTIK_KEY_FILE"] = str(_TMP / "secret.key")
os.environ["MTIK_SCHEDULER_ENABLED"] = "false"
os.environ["MTIK_BASE_DIR"] = str(_TMP)
