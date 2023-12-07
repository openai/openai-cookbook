def check_context(title, heading, question, max_len=1800, search_model='ada', max_rerank=10):
    """
    Evaluate the performance of the search model in retrieving the correct context

    Parameters
    ----------
    title: str
        The title of the Wikipedia page
    heading: str
        The heading of the Wikipedia section
    qusetion: str
        The question
    max_len: int
        The maximum length of the context
    search_model: str
        The search model to use - `ada` is most cost effective
    max_rerank: int
        The maximum number of reranking documents to use the search model on

    Returns
    -------
    rank: int
        The rank of the correct context
    token_length: int
        The number of tokens needed to obtain the correct context
    """
    
    try:
        results = openai.Engine(search_model).search(
            search_model=search_model, 
            query=question, 
            max_rerank=max_rerank,
            file=olympics_search_fileid,
            return_metadata=True
        )
        index=-1
        returns = []
        cur_len = 0
        for result in results['data']:
            cur_len += int(result['metadata']) + 4 # we add 4 tokens for the separator `\n\n###\n\n`
            if cur_len > max_len:
                break
            returns.append(result['text'])
            res = result['text'].split('\n')
            if res[0] == title and res[1] == heading:
                index = len(returns) - 1
                break
        return index, cur_len
    except Exception as e:
        #print (e)
        return []
print(check_context("Athletics at the 2020 Summer Olympics – Women's 4 × 100 metres relay", "Summary", "Where did women's 4 x 100 metres relay event take place during the 2020 Summer Olympics?", max_len=10000))