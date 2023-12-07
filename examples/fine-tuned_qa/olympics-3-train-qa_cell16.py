ft_discriminator = "curie:ft-openai-internal-2021-08-23-23-58-57"
ft_qa = "curie:ft-openai-internal-2021-08-23-17-54-10"

def apply_ft_discriminator(context, question, discriminator_model):
    """
    Apply the fine tuned discriminator to a question, to assess whether it can be answered from the context.
    """
    prompt = f"{context}\nQuestion: {question}\n Related:"
    result = openai.Completion.create(model=discriminator_model, prompt=prompt, max_tokens=1, temperature=0, top_p=1, n=1, logprobs=2)
    return result['choices'][0]['logprobs']['top_logprobs']

apply_ft_discriminator('The first human-made object in space was the Soviet Union satellite Sputnik 1 on 4 October 1957.', 
                        'What was the first human-made object in space?', ft_discriminator)