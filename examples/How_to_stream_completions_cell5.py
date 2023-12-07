reply = response['choices'][0]['message']
print(f"Extracted reply: \n{reply}")

reply_content = response['choices'][0]['message']['content']
print(f"Extracted content: \n{reply_content}")
