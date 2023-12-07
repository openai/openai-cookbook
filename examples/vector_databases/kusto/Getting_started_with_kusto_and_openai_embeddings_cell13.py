import pandas as pd

from ast import literal_eval

article_df = pd.read_csv('/lakehouse/default/Files/data/vector_database_wikipedia_articles_embedded.csv')
# Read vectors from strings back into a list
article_df["title_vector"] = article_df.title_vector.apply(literal_eval)
article_df["content_vector"] = article_df.content_vector.apply(literal_eval)
article_df.head()
