# estimate inference cost assuming gpt-3.5-turbo (4K context)
i_tokens  = result["model_response"]["usage"]["prompt_tokens"] 
o_tokens = result["model_response"]["usage"]["completion_tokens"] 

i_cost = (i_tokens / 1000) * 0.0015
o_cost = (o_tokens / 1000) * 0.002

print(f"""Token Usage
    Prompt: {i_tokens} tokens
    Completion: {o_tokens} tokens
    Cost estimation: ${round(i_cost + o_cost, 5)}""")