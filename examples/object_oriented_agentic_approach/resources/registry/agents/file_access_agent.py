import logging
import os

# Import base classes
from ...object_oriented_agents.utils.logger import get_logger
from ...object_oriented_agents.core_classes.base_agent import BaseAgent
from ...object_oriented_agents.core_classes.tool_manager import ToolManager
from ...object_oriented_agents.services.openai_language_model import OpenAILanguageModel

# Import the Tool
from ..tools.file_access_tool import FileAccessTool

# Set the verbosity level: DEBUG for verbose output, INFO for normal output, and WARNING/ERROR for minimal output
myapp_logger = get_logger("MyApp", level=logging.INFO)

# Create a LanguageModelInterface instance using the OpenAILanguageModel
language_model_api_interface = OpenAILanguageModel(api_key=os.getenv("OPENAI_API_KEY"), logger=myapp_logger)


class FileAccessAgent(BaseAgent):
    """
    Agent that can only use the 'safe_file_access' tool to read CSV files.
    """
    # We pass the Agent attributes in the constructor 
    def __init__(self, 
                 developer_prompt: str = """
                 You are a helpful data science assistant. The user will provide the name of a CSV file that contains relational data. The file is in the directory ./resources/data

                 Instructions:
                 1. When the user provides the CSV file name, use the 'safe_read_file' tool to read and display the first 15 lines of that file.
                 2. If the specified file does not exist in the provided directory, return an appropriate error message (e.g., "Error: The specified file does not exist in the provided directory").
                 3. The user may request data analysis based on the file’s contents, but you should NOT perform or write code for any data analysis. Your only task is to read and return the first 6 lines of the file.

                 Do not include any additional commentary or code not related to reading the file.
                 """,
                 model_name: str = "gpt-4o",
                 logger = myapp_logger,
                 language_model_interface = language_model_api_interface):
        super().__init__(developer_prompt=developer_prompt, model_name=model_name, logger=logger, language_model_interface=language_model_interface)
        self.setup_tools()

    def setup_tools(self) -> None:
        self.logger.debug("Setting up tools for FileAccessAgent.")
        # Pass the openai_client to ToolManager
        self.tool_manager = ToolManager(logger=self.logger, language_model_interface=self.language_model_interface)
        # Register the one tool this agent is allowed to use
        self.tool_manager.register_tool(FileAccessTool(logger=self.logger))