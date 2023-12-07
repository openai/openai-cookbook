import pandas as pd

from ast import literal_eval

# read data from csv
article_df = pd.read_csv('../data/vector_database_wikipedia_articles_embedded.csv')
article_df = article_df[['id', 'url', 'title', 'text', 'content_vector']]

# read vectors from strings back into a list
article_df["content_vector"] = article_df.content_vector.apply(literal_eval)
article_df.head()