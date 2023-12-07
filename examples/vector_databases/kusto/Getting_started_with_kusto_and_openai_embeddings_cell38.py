KUSTO_QUERY = "Wiki | extend similarity = series_cosine_similarity_fl(dynamic("+str(searchedEmbedding)+"), title_vector,1,1) | top 10 by similarity desc "
RESPONSE = KUSTO_CLIENT.execute(KUSTO_DATABASE, KUSTO_QUERY)

df = dataframe_from_result_table(RESPONSE.primary_results[0])
df