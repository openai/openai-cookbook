HA_INPUT = f"""
Generate a hypothetical answer to the user's question. This answer will be used to rank search results. 
Pretend you have all the information you need to answer, but don't use any actual facts. Instead, use placeholders
like NAME did something, or NAME said something at PLACE. 

User question: {USER_QUESTION}

Format: {{"hypotheticalAnswer": "hypothetical answer text"}}
"""

hypothetical_answer = json_gpt(HA_INPUT)["hypotheticalAnswer"]

hypothetical_answer
