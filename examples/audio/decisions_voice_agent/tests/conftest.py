"""Import only the public evaluation contract, without vendoring its harness."""

import importlib.util
import sys
from pathlib import Path

# Import the actual public contract source. The parent package's __init__ eagerly
# imports its complete audio/SDK stack, which these offline tests do not need.
path = (
    Path(__file__).resolve().parents[2]
    / "duplex_voice_agent_evaluation/assistants/client/backend.py"
)
spec = importlib.util.spec_from_file_location("cookbook_evaluation_backend", path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
