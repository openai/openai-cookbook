ada_results = df.apply(lambda x: [
                    check_context( x.title, 
                                   x.heading, 
                                   q[3:],     # remove the number prefix
                                   max_len=1000000, # set a large number to get the full context 
                                   search_model='ada', 
                                   max_rerank=200,
                                 ) 
                    for q in (x.questions).split('\n') # split the questions
                    if len(q) >10 # remove the empty questions
                ], axis=1)
ada_results.head()