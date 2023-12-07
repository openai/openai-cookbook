def group_chunks(chunks, ntokens, max_len=1000, hard_max_len=3000):
    """
    Group very short chunks, to form approximately page long chunks.
    """
    batches = []
    cur_batch = ""
    cur_tokens = 0
    
    # iterate over chunks, and group the short ones together
    for chunk, ntoken in zip(chunks, ntokens):
        # discard chunks that exceed hard max length
        if ntoken > hard_max_len:
            print(f"Warning: Chunk discarded for being too long ({ntoken} tokens > {hard_max_len} token limit). Preview: '{chunk[:50]}...'")
            continue

        # if room in current batch, add new chunk
        if cur_tokens + 1 + ntoken <= max_len:
            cur_batch += "\n\n" + chunk
            cur_tokens += 1 + ntoken  # adds 1 token for the two newlines
        # otherwise, record the batch and start a new one
        else:
            batches.append(cur_batch)
            cur_batch = chunk
            cur_tokens = ntoken
            
    if cur_batch:  # add the last batch if it's not empty
        batches.append(cur_batch)
        
    return batches


chunks = group_chunks(chunks, ntokens)
len(chunks)