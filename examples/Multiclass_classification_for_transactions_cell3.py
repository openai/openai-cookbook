import openai
import pandas as pd
import numpy as np
import json
import os

openai.api_key = os.getenv("OPENAI_API_KEY")
COMPLETIONS_MODEL = "text-davinci-002"
