test_set['result'] = test_set.apply(lambda x: str(x['pred']).strip() == str(x['completion']).strip(), axis = 1)
