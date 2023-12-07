from getpass import getpass
from collections import Counter

import cassio
from cassio.table import MetadataVectorCassandraTable

import openai
from datasets import load_dataset