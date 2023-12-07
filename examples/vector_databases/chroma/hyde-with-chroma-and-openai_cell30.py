def build_prompt_with_context(claim, context):
    return [{'role': 'system', 'content': "I will ask you to assess whether a particular scientific claim, based on evidence provided. Output only the text 'True' if the claim is true, 'False' if the claim is false, or 'NEE' if there's not enough evidence."}, 
            {'role': 'user', 'content': f""""
The evidence is the following:

{' '.join(context)}

Assess the following claim on the basis of the evidence. Output only the text 'True' if the claim is true, 'False' if the claim is false, or 'NEE' if there's not enough evidence. Do not output any other text. 

Claim:
{claim}

Assessment:
"""}]


def assess_claims_with_context(claims, contexts):
    responses = []
    # Query the OpenAI API
    for claim, context in zip(claims, contexts):
        # If no evidence is provided, return NEE
        if len(context) == 0:
            responses.append('NEE')
            continue
        response = openai.ChatCompletion.create(
            model='gpt-3.5-turbo',
            messages=build_prompt_with_context(claim=claim, context=context),
            max_tokens=3,
        )
        # Strip any punctuation or whitespace from the response
        responses.append(response.choices[0].message.content.strip('., '))

    return responses