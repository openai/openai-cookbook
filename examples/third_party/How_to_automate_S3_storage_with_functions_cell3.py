import openai
import json
import boto3
import os
import datetime
from urllib.request import urlretrieve

# load environment variables
from dotenv import load_dotenv
load_dotenv() 