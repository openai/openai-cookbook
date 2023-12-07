from redis.commands.search.query import Query
import numpy as np

vec = np.array(openai.Embedding.create(input = [prompt], model = model)['data'][0]['embedding'], dtype=np.float32).tobytes()
q = Query('*=>[KNN 1 @vector $query_vec AS vector_score]')\
    .sort_by('vector_score')\
    .return_fields('content')\
    .dialect(2)    
params = {"query_vec": vec}

context = client.ft('idx').search(q, query_params=params).docs[0].content
print(context)