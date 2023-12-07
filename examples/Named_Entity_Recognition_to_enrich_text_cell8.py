import json
import logging
import os

import openai
import wikipedia

from typing import Optional
from IPython.display import display, Markdown
from tenacity import retry, wait_random_exponential, stop_after_attempt

logging.basicConfig(level=logging.INFO, format=' %(asctime)s - %(levelname)s - %(message)s')

OPENAI_MODEL = 'gpt-3.5-turbo-0613'
openai.api_key = os.getenv("OPENAI_API_KEY")