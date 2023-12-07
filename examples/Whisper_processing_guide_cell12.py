# Define function to add punctuation
def punctuation_assistant(ascii_transcript):

    system_prompt = """You are a helpful assistant that adds punctuation to text.
      Preserve the original words and only insert necessary punctuation such as periods,
     commas, capialization, symbols like dollar sings or percentage signs, and formatting.
     Use only the context provided. If there is no context provided say, 'No context provided'\n"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": ascii_transcript
            }
        ]
    )
    return response
