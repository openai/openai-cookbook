import random

def get_random_similar_contexts(question, context, file_id=olympics_search_fileid, search_model='ada', max_rerank=10):
    """
    Find similar contexts to the given context using the search file
    """
    try:
        results = openai.Engine(search_model).search(
            search_model=search_model, 
            query=question, 
            max_rerank=max_rerank,
            file=file_id
        )
        candidates = []
        for result in results['data'][:3]:
            if result['text'] == context:
                continue
            candidates.append(result['text'])
        random_candidate = random.choice(candidates)
        return random_candidate
    except Exception as e:
        print(e)
        return ""

def create_fine_tuning_dataset(df, discriminator=False, n_negative=1, add_related=False):
    """
    Create a dataset for fine tuning the OpenAI model; either for a discriminator model, 
    or a model specializing in Q&A, where it says if no relevant context is found.

    Parameters
    ----------
    df: pd.DataFrame
        The dataframe containing the question, answer and context pairs
    discriminator: bool
        Whether to create a dataset for the discriminator
    n_negative: int
        The number of random negative samples to add (using a random context)
    add_related: bool
        Whether to add the related contexts to the correct context. These are hard negative examples

    Returns
    -------
    pd.DataFrame
        The dataframe containing the prompts and completions, ready for fine-tuning
    """
    rows = []
    for i, row in df.iterrows():
        for q, a in zip(("1." + row.questions).split('\n'), ("1." + row.answers).split('\n')):
            if len(q) >10 and len(a) >10:
                if discriminator:
                    rows.append({"prompt":f"{row.context}\nQuestion: {q[2:].strip()}\n Related:", "completion":f" yes"})
                else:
                    rows.append({"prompt":f"{row.context}\nQuestion: {q[2:].strip()}\nAnswer:", "completion":f" {a[2:].strip()}"})

    for i, row in df.iterrows():
        for q in ("1." + row.questions).split('\n'):
            if len(q) >10:
                for j in range(n_negative + (2 if add_related else 0)):
                    random_context = ""
                    if j == 0 and add_related:
                        # add the related contexts based on originating from the same wikipedia page
                        subset = df[(df.title == row.title) & (df.context != row.context)]
                        
                        if len(subset) < 1:
                            continue
                        random_context = subset.sample(1).iloc[0].context
                    if j == 1 and add_related:
                        # add the related contexts based on the most similar contexts according to the search
                        random_context = get_random_similar_contexts(q[2:].strip(), row.context, search_model='ada', max_rerank=10)
                    else:
                        while True:
                            # add random context, which isn't the correct context
                            random_context = df.sample(1).iloc[0].context
                            if random_context != row.context:
                                break
                    if discriminator:
                        rows.append({"prompt":f"{random_context}\nQuestion: {q[2:].strip()}\n Related:", "completion":f" no"})
                    else:
                        rows.append({"prompt":f"{random_context}\nQuestion: {q[2:].strip()}\nAnswer:", "completion":f" No appropriate context found to answer the question."})

    return pd.DataFrame(rows) 