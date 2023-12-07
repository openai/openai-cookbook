summary = openai.ChatCompletion.create(
  model="gpt-3.5-turbo",
  messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Answer the following question:" 
         + question 
         + "by using the following text:" 
         + top_hit_summary},
    ]
)

choices = summary.choices

for choice in choices:
    print("------------------------------------------------------------")
    print(choice.message.content)
    print("------------------------------------------------------------")