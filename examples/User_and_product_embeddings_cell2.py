import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from ast import literal_eval

df = pd.read_csv('data/fine_food_reviews_with_embeddings_1k.csv', index_col=0)  # note that you will need to generate this file to run the code below
df.head(2)