import openai
import numpy as np
import json
import os
from openai import OpenAI
import itertools
from tenacity import retry, wait_random_exponential, stop_after_attempt
from typing import Any, Dict, List, Generator
import ast
client = OpenAI()
