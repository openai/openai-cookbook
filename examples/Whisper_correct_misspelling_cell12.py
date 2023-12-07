# define a wrapper function for seeing how prompts affect transcriptions
def transcribe_with_spellcheck(system_message, audio_filepath):
    completion = openai.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": transcribe(prompt="", audio_filepath=audio_filepath),
            },
        ],
    )
    return completion.choices[0].message.content
