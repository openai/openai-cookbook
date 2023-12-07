# imports
import pandas as pd
import numpy as np
from typing import List

from utils.embeddings_utils import (
    get_embeddings,
    distances_from_embeddings,
    tsne_components_from_embeddings,
    chart_from_components,
    indices_of_nearest_neighbors_from_distances,
)

# constants
EMBEDDING_MODEL = "text-embedding-ada-002"

# load in data and clean data types and drop null rows
df = pd.read_csv("../../data/styles_2k.csv", on_bad_lines='skip')
df.dropna(inplace=True)
df["year"] = df["year"].astype(int)
df.info()

# print dataframe
n_examples = 5
df.head(n_examples)
