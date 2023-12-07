# set index parameters
index = "openai_test"
embedding_dim = 1536
distance_type = "L2"
index_type = "HNSW"
data_type = "FLOAT32"

# Create two indexes, one for title_vector and one for content_vector, skip if already exists
index_names = [index + "_title_vector", index+"_content_vector"]
for index_name in index_names:
    index_connection = client.tvs_get_index(index_name)
    if index_connection is not None:
        print("Index already exists")
    else:
        client.tvs_create_index(name=index_name, dim=embedding_dim, distance_type=distance_type,
                                index_type=index_type, data_type=data_type)