import os
import tempfile

# Tests never read or write the real saved model settings.
os.environ["RECAST_DATA_DIR"] = tempfile.mkdtemp(prefix="recast-test-")
os.environ["LLM_PROVIDER"] = "demo"
