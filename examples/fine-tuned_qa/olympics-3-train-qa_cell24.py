def answer_question_conditionally(answering_model, discriminator_model, context, question, discriminator_logprob_yes_modifier=0):
    logprobs = apply_ft_discriminator(context, question, discriminator_model)
    yes_logprob = logprobs[' yes'] if ' yes' in logprobs else -100
    no_logprob = logprobs[' no'] if ' no' in logprobs else -100
    if yes_logprob + discriminator_logprob_yes_modifier < no_logprob:
        return " No appropriate context found to answer the question based on the discriminator."
    return apply_ft_qa_answer(context, question, answering_model)
answer_question_conditionally(ft_qa, ft_discriminator, 
                                "Crowdless games are a rare although not unheard-of occurrence in sports. \
                                 When they do occur, it is usually the result of events beyond the control \
                                 of the teams or fans, such as weather-related concerns, public health concerns, \
                                 or wider civil disturbances unrelated to the game. For instance, \
                                 the COVID-19 pandemic caused many sports leagues around the world \
                                 to be played behind closed doors.",
                                "Could weather cause a sport event to have no crowd?")