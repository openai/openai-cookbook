import logging
import os

# Import base classes
from ...object_oriented_agents.utils.logger import get_logger
from ...object_oriented_agents.core_classes.base_agent import BaseAgent
from ...object_oriented_agents.core_classes.tool_manager import ToolManager
from ...object_oriented_agents.services.openai_language_model import OpenAILanguageModel

# Import the Python Code Interpreter tool
from ..tools.python_code_interpreter_tool import PythonExecTool

# Set the verbosity level: DEBUG for verbose output, INFO for normal output, and WARNING/ERROR for minimal output
myapp_logger = get_logger("MyApp", level=logging.INFO)

# Create a LanguageModelInterface instance using the OpenAILanguageModel
language_model_api_interface = OpenAILanguageModel(api_key=os.getenv("OPENAI_API_KEY"), logger=myapp_logger)


class PythonExecAgent(BaseAgent):
    """
    An agent specialized in executing Python code in a Docker container.
    """

    def __init__(
            self,
            developer_prompt: str = """  
                    You are a helpful data science assistant. Your tasks include analyzing CSV data and generating Python code to address user queries. Follow these guidelines:

                    1. The user will provide the name of a CSV file located in the directory `/home/sandboxuser`.
                    2. The user will also supply context, including:
                    - Column names and their descriptions.
                    - Sample data from the CSV (headers and a few rows) to help understand data types.
                    3. Generate Python code to analyze the data and call the tool `execute_python_code` to run the code and get results.
                    4. You can use Python libraries pandas, numpy, matplotlib, seaborn, and scikit-learn. 
                    5. Interpret the results of the code execution and provide analysis to the user. 
                """,
            model_name: str = "o3-mini",
            logger=myapp_logger,
            language_model_interface=language_model_api_interface,
            reasoning_effort: str = None  # optional; if provided, passed to API calls
    ):
        super().__init__(
            developer_prompt=developer_prompt,
            model_name=model_name,
            logger=logger,
            language_model_interface=language_model_interface,
            reasoning_effort=reasoning_effort
        )
        self.setup_tools()

    def setup_tools(self) -> None:
        """
        Create a ToolManager, instantiate the PythonExecTool and register it with the ToolManager.
        """
        self.tool_manager = ToolManager(logger=self.logger, language_model_interface=self.language_model_interface)

        # Create the Python execution tool
        python_exec_tool = PythonExecTool()

        # Register the Python execution tool
        self.tool_manager.register_tool(python_exec_tool)