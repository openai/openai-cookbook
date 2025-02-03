# object_oriented_agents/core_classes/agent_signature.py

from typing import Optional, Dict, Any, List
from .tool_manager import ToolManager

class AgentSignature:
    """
    Encapsulates the logic to produce an agent's 'signature' data:
    - The developer prompt
    - The model name
    - The list of tool definitions
    - The default reasoning effort (if any)
    """

    def __init__(self, developer_prompt: str, model_name: str, tool_manager: Optional[ToolManager] = None, reasoning_effort: Optional[str] = None):
        self.developer_prompt = developer_prompt
        self.model_name = model_name
        self.tool_manager = tool_manager
        self.reasoning_effort = reasoning_effort

    def to_dict(self) -> Dict[str, Any]:
        """
        Return a dictionary containing:
          1. The developer prompt
          2. The model name
          3. A list of tool definitions (function schemas)
          4. The default reasoning effort if defined
        """
        if self.tool_manager:
            # Each item in get_tool_definitions() looks like {"type": "function", "function": {...}}
            tool_definitions = self.tool_manager.get_tool_definitions()
            functions = [t for t in tool_definitions]
        else:
            functions = []

        signature_dict = {
            "developer_prompt": self.developer_prompt,
            "model_name": self.model_name,
            "tools": functions
        }
        if self.reasoning_effort is not None:
            signature_dict["reasoning_effort"] = self.reasoning_effort

        return signature_dict