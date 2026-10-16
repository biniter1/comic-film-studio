"""Test-wide setup: every test session uses a throw-away data dir (never the user's)."""

import os
import tempfile

os.environ["CFS_DATA_DIR"] = tempfile.mkdtemp(prefix="cfs-test-")
