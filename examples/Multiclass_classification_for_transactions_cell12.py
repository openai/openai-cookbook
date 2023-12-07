test_transactions = transactions.iloc[:25]
test_transactions['Classification'] = test_transactions.apply(lambda x: classify_transaction(x,zero_shot_prompt),axis=1)
