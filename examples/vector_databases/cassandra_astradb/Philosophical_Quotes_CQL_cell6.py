import os
from uuid import uuid4
from getpass import getpass
from collections import Counter

from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

import openai
from datasets import load_dataset