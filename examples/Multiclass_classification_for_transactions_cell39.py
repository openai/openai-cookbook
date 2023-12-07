test_set['predicted_class'] = test_set.apply(lambda x: openai.Completion.create(model=fine_tuned_model, prompt=x['prompt'], max_tokens=1, temperature=0, logprobs=5),axis=1)
test_set['pred'] = test_set.apply(lambda x : x['predicted_class']['choices'][0]['text'],axis=1)
