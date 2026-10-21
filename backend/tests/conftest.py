import os
import tempfile

_TEST_ROOT = tempfile.mkdtemp(prefix="workbench-test-")
os.environ.setdefault("WORKBENCH_DATA", os.path.join(_TEST_ROOT, "data"))
os.environ.setdefault("WORKBENCH_DAILY_PAPER_DIR", os.path.join(_TEST_ROOT, "daily_paper"))
