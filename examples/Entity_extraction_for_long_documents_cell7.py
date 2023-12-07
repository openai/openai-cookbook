# Initialise tokenizer
tokenizer = tiktoken.get_encoding("cl100k_base")

results = []
    
chunks = create_chunks(clean_text,1000,tokenizer)
text_chunks = [tokenizer.decode(chunk) for chunk in chunks]

for chunk in text_chunks:
    results.append(extract_chunk(chunk,template_prompt))
    #print(chunk)
    print(results[-1])
