# Test to ensure that your OpenAI API key is defined as an environment variable or provide it when prompted
# If you run this notebook locally, you may have to reload the terminal and the notebook to make the environment available

import os
from getpass import getpass

# Check if OPENAI_API_KEY is set as an environment variable
if os.getenv("OPENAI_API_KEY") is not None:
    print("Your OPENAI_API_KEY is ready")
else:
    # If not, prompt for it
    api_key = getpass("Enter your OPENAI_API_KEY: ")
    if api_key:
        print("Your OPENAI_API_KEY is now available for this session")
        # Optionally, you can set it as an environment variable for the current session
        os.environ["OPENAI_API_KEY"] = api_key
    else:
        print("You did not enter your OPENAI_API_KEY")