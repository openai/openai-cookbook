# install packages

!python3 -m pip install -qU openai pandas wget elasticsearch

# import modules

from getpass import getpass
from elasticsearch import Elasticsearch, helpers
import wget
import zipfile
import pandas as pd
import json
import openai