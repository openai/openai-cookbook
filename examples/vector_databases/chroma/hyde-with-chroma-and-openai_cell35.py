def filter_query_result(query_result, distance_threshold=0.25):
# For each query result, retain only the documents whose distance is below the threshold
    for ids, docs, distances in zip(query_result['ids'], query_result['documents'], query_result['distances']):
        for i in range(len(ids)-1, -1, -1):
            if distances[i] > distance_threshold:
                ids.pop(i)
                docs.pop(i)
                distances.pop(i)
    return query_result
