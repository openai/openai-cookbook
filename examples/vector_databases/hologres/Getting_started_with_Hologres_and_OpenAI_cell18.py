title_vector_length = len(json.loads(data['title_vector'].iloc[0]))
content_vector_length = len(json.loads(data['content_vector'].iloc[0]))

print(title_vector_length, content_vector_length)