holdout_df['combined'] = "Supplier: " + holdout_df['Supplier'].str.strip() + "; Description: " + holdout_df['Description'].str.strip() + '\n\n###\n\n' # + "; Value: " + str(df['Transaction value (£)']).strip()
holdout_df['prediction_result'] = holdout_df.apply(lambda x: openai.Completion.create(model=fine_tuned_model, prompt=x['combined'], max_tokens=1, temperature=0, logprobs=5),axis=1)
holdout_df['pred'] = holdout_df.apply(lambda x : x['prediction_result']['choices'][0]['text'],axis=1)
