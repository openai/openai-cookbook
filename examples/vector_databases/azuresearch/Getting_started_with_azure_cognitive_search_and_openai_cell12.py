article_df = pd.read_csv('../../data/vector_database_wikipedia_articles_embedded.csv')  
  
# Read vectors from strings back into a list using json.loads  
article_df["title_vector"] = article_df.title_vector.apply(json.loads)  
article_df["content_vector"] = article_df.content_vector.apply(json.loads)  
article_df['vector_id'] = article_df['vector_id'].apply(str)  
article_df.head()  
