import os

import arxiv
import ast
import concurrent
from csv import writer
from IPython.display import display, Markdown, Latex
import json
import openai
import os
import pandas as pd
from PyPDF2 import PdfReader
import requests
from scipy import spatial
from tenacity import retry, wait_random_exponential, stop_after_attempt
import tiktoken
from tqdm import tqdm
from termcolor import colored

GPT_MODEL = "gpt-3.5-turbo-0613"
EMBEDDING_MODEL = "text-embedding-ada-002"
