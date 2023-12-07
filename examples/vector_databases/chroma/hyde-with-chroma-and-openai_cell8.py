def build_prompt(claim):
    return [
        {"role": "system", "content": "I will ask you to assess a scientific claim. Output only the text 'True' if the claim is true, 'False' if the claim is false, or 'NEE' if there's not enough evidence."},
        {"role": "user", "content": f"""        
Example:

Claim:
0-dimensional biomaterials show inductive properties.

Assessment:
False

Claim:
1/2000 in UK have abnormal PrP positivity.

Assessment:
True

Claim:
Aspirin inhibits the production of PGE2.

Assessment:
False

End of examples. Assess the following claim:

Claim:
{claim}

Assessment:
"""}
    ]


def assess_claims(claims):
    responses = []
    # Query the OpenAI API
    for claim in claims:
        response = openai.ChatCompletion.create(
            model='gpt-3.5-turbo',
            messages=build_prompt(claim),
            max_tokens=3,
        )
        # Strip any punctuation or whitespace from the response
        responses.append(response.choices[0].message.content.strip('., '))

    return responses