# Get a test transaction
transaction = transactions.iloc[0]

# Interpolate the values into the prompt
prompt = zero_shot_prompt.replace('SUPPLIER_NAME',transaction['Supplier'])
prompt = prompt.replace('DESCRIPTION_TEXT',transaction['Description'])
prompt = prompt.replace('TRANSACTION_VALUE',str(transaction['Transaction value (£)']))

# Use our completion function to return a prediction
completion_response = request_completion(prompt)
print(completion_response.choices[0].text)
