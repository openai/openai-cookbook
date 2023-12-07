from redis.commands.search.query import Query
import numpy as np

text_4 = """Radcliffe yet to answer GB call

Paula Radcliffe has been granted extra time to decide whether to compete in the World Cross-Country Championships.

The 31-year-old is concerned the event, which starts on 19 March in France, could upset her preparations for the London Marathon on 17 April. "There is no question that Paula would be a huge asset to the GB team," said Zara Hyde Peters of UK Athletics. "But she is working out whether she can accommodate the worlds without too much compromise in her marathon training." Radcliffe must make a decision by Tuesday - the deadline for team nominations. British team member Hayley Yelling said the team would understand if Radcliffe opted out of the event. "It would be fantastic to have Paula in the team," said the European cross-country champion. "But you have to remember that athletics is basically an individual sport and anything achieved for the team is a bonus. "She is not messing us around. We all understand the problem." Radcliffe was world cross-country champion in 2001 and 2002 but missed last year's event because of injury. In her absence, the GB team won bronze in Brussels.
"""

vec = np.array(get_vector(text_4), dtype=np.float32).tobytes()
q = Query('*=>[KNN 3 @vector $query_vec AS vector_score]')\
    .sort_by('vector_score')\
    .return_fields('vector_score', 'content')\
    .dialect(2)    
params = {"query_vec": vec}

results = client.ft('idx').search(q, query_params=params)
for doc in results.docs:
    print(f"distance:{round(float(doc['vector_score']),3)} content:{doc['content']}\n")
