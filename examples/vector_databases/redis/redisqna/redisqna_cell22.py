prompt = f"""
Using the information delimited by triple backticks, answer this question: Is Sam Bankman-Fried's company, FTX, considered a well-managed company?

Context: ```{context}```
"""

response = get_completion(prompt)
print(response)