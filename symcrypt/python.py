"""Run upstream SymCrypt scripts with the declared Python and pyelftools."""
import os
import sys

os.environ["PYTHONPATH"] = os.pathsep.join(sys.path)
# Upstream scripts import helpers beside the script, as normal Python does.
# The Bazel launcher's safe-path setting must not suppress that declared input.
os.environ.pop("PYTHONSAFEPATH", None)
os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
