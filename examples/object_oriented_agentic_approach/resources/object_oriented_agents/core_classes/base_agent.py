# object_oriented_agents/core_classes/base_agent.py

from abc import ABC, abstractmethod
from typing import Optional
from .chat_messages import ChatMessages
from .tool_manager import ToolManager
from ..utils.logger import get_logger
from ..services.language_model_interface import LanguageModelInterface
from .agent_signature import AgentSignature


class BaseAgent(ABC):
    """
    An abstract base agent that defines the high-level approach to handling user tasks
    and orchestrating calls to the OpenAI API.
    """

    def __init__(
            self,
            developer_prompt: str,
            model_name: str,
            logger=None,
            language_model_interface: LanguageModelInterface = None,
            reasoning_effort: Optional[str] = None
    ):
        self.developer_prompt = developer_prompt
        self.model_name = model_name
        self.messages = ChatMessages(developer_prompt)
        self.tool_manager: Optional[ToolManager] = None
        self.logger = logger or get_logger(self.__class__.__name__)
        self.language_model_interface = language_model_interface
        self.reasoning_effort = reasoning_effort

    @abstractmethod
    def setup_tools(self) -> None:
        pass

    def add_context(self, content: str) -> None:
        self.logger.debug(f"Adding context: {content}")
        self.messages.add_user_message(content)

    def add_message(self, content: str) -> None:
        self.logger.debug(f"Adding user message: {content}")
        self.messages.add_user_message(content)

    def task(self, user_task: str, tool_call_enabled: bool = True, return_tool_response_as_is: bool = False,
             reasoning_effort: Optional[str] = None) -> str:
        # Use the reasoning_effort provided in the method call if present, otherwise fall back to the agent's default
        final_reasoning_effort = reasoning_effort if reasoning_effort is not None else self.reasoning_effort

        if self.language_model_interface is None:
            error_message = "Error: Cannot execute task without the LanguageModelInterface."
            self.logger.error(error_message)
            raise ValueError(error_message)

        self.logger.debug(f"Starting task: {user_task} (tool_call_enabled={tool_call_enabled})")

        # Add user message
        self.add_message(user_task)

        tools = []
        if tool_call_enabled and self.tool_manager:
            tools = self.tool_manager.get_tool_definitions()
            self.logger.debug(f"Tools available: {tools}")

        # Build parameter dict and include reasoning_effort only if not None
        params = {
            "model": self.model_name,
            "messages": self.messages.get_messages(),
            "tools": tools
        }
        if final_reasoning_effort is not None:
            params["reasoning_effort"] = final_reasoning_effort

        self.logger.debug("Sending request to language model interface...")
        response = self.language_model_interface.generate_completion(**params)

        tool_calls = response.choices[0].message.tool_calls
        if tool_call_enabled and self.tool_manager and tool_calls:
            self.logger.debug(f"Tool calls requested: {tool_calls}")
            return self.tool_manager.handle_tool_call_sequence(
                response,
                return_tool_response_as_is,
                self.messages,
                self.model_name,
                reasoning_effort=final_reasoning_effort
            )

        # No tool call, normal assistant response
        response_message = response.choices[0].message.content
        self.messages.add_assistant_message(response_message)
        self.logger.debug("Task completed successfully.")
        return response_message

    def signature(self) -> dict:
        """
        Return a dictionary with:
        - The developer prompt
        - The model name
        - The tool definitions (function schemas)
        - The default reasoning effort if set
        """
        signature_obj = AgentSignature(
            developer_prompt=self.developer_prompt,
            model_name=self.model_name,
            tool_manager=self.tool_manager,
            reasoning_effort=self.reasoning_effort
        )
        return signature_obj.to_dict()