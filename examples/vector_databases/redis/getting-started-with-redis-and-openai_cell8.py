import sys
import numpy as np
import pandas as pd
from typing import List

# use helper function in nbutils.py to download and read the data
# this should take from 5-10 min to run
if os.getcwd() not in sys.path:
    sys.path.append(os.getcwd())
import nbutils

nbutils.download_wikipedia_data()
data = nbutils.read_wikipedia_data()

data.head()