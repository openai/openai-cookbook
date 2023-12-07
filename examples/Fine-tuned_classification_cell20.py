results = pd.read_csv('result.csv')
results[results['classification/accuracy'].notnull()].tail(1)