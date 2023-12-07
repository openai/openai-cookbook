import pandas as pd
import numpy as np
from ast import literal_eval

# Load the embeddings
datafile_path = "data/fine_food_reviews_with_embeddings_1k.csv"
df = pd.read_csv(datafile_path)

# Convert to a list of lists of floats
embeddings = np.array(df.embedding.apply(literal_eval).to_list())
df = df.drop('embedding', axis=1)
df = df.rename(columns={'Unnamed: 0': 'id'})
