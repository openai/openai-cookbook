import pandas as pd
from ast import literal_eval
# Path to your local CSV file
csv_file_path = '../../data/vector_database_wikipedia_articles_embedded.csv'
article_df = pd.read_csv(csv_file_path)

# Read vectors from strings back into a list
article_df['title_vector'] = article_df.title_vector.apply(literal_eval).values
article_df['content_vector'] = article_df.content_vector.apply(literal_eval).values

# add/update data to indexes
for i in range(len(article_df)):
    # add data to index with title_vector
    client.tvs_hset(index=index_names[0], key=article_df.id[i].item(), vector=article_df.title_vector[i], is_binary=False,
                    **{"url": article_df.url[i], "title": article_df.title[i], "text": article_df.text[i]})
    # add data to index with content_vector
    client.tvs_hset(index=index_names[1], key=article_df.id[i].item(), vector=article_df.content_vector[i], is_binary=False,
                    **{"url": article_df.url[i], "title": article_df.title[i], "text": article_df.text[i]})