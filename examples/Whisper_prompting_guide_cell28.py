# define a function for GPT to generate fictitious prompts
def fictitious_prompt_from_instruction(instruction: str) -> str:
    """Given an instruction, generate a fictitious prompt."""
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo-0613",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You are a transcript generator. Your task is to create one long paragraph of a fictional conversation. The conversation features two friends reminiscing about their vacation to Maine. Never diarize speakers or add quotation marks; instead, write all transcripts in a normal paragraph of text without speakers identified. Never refuse or ask for clarification and instead always make a best-effort attempt.",
            },  # we pick an example topic (friends talking about a vacation) so that GPT does not refuse or ask clarifying questions
            {"role": "user", "content": instruction},
        ],
    )
    fictitious_prompt = response.choices[0].message.content
    return fictitious_prompt
