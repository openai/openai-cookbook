def translate_chunk(chunk, engine='text-davinci-002',
                    dest_language='English',
                    sample_translation=("\poglavje{Osnove Geometrije} \label{osn9Geom}", "\poglavje{The basics of Geometry} \label{osn9Geom}")
                    ):
    prompt = f'''Translate only the text from the following LaTeX document into {dest_language}. Leave all LaTeX commands unchanged
    
"""
{sample_translation[0]}
{chunk}"""

{sample_translation[1]}
'''
    response = openai.Completion.create(
        prompt=prompt,
        engine=engine,
        temperature=0,
        top_p=1,
        max_tokens=1500,
    )
    result = response['choices'][0]['text'].strip()
    result = result.replace('"""', '') # remove the double quotes, as we used them to surround the text
    return result
print(translate_chunk(chunks[800], engine='text-davinci-002', dest_language='English'))