KUSTO_QUERY = "Wiki | extend similarity = series_cosine_similarity_fl(dynamic("+str(searchedEmbedding)+"), content_vector,1,1) | top 10 by similarity desc "

RESPONSE = KUSTO_CLIENT.execute(KUSTO_DATABASE, KUSTO_QUERY)