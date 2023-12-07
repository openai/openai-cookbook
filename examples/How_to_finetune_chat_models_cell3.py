import json
import openai
import os
import pandas as pd
from pprint import pprint

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
openai.api_key = OPENAI_API_KEY