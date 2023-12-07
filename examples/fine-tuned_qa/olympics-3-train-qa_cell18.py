def apply_ft_qa_answer(context, question, answering_model):
    """
    Apply the fine tuned discriminator to a question
    """
    prompt = f"{context}\nQuestion: {question}\nAnswer:"
    result = openai.Completion.create(model=answering_model, prompt=prompt, max_tokens=30, temperature=0, top_p=1, n=1, stop=['.','\n'])
    return result['choices'][0]['text']

apply_ft_qa_answer('The first human-made object in space was the Soviet Union satellite Sputnik 1 on 4 October 1957.', 
                    'What was the first human-made object in space?', ft_qa)
