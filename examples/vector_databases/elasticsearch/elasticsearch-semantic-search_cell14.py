def dataframe_to_bulk_actions(df):
    for index, row in df.iterrows():
        yield {
            "_index": 'wikipedia_vector_index',
            "_id": row['id'],
            "_source": {
                'url' : row["url"],
                'title' : row["title"],
                'text' : row["text"],
                'title_vector' : json.loads(row["title_vector"]),
                'content_vector' : json.loads(row["content_vector"]),
                'vector_id' : row["vector_id"]
            }
        }