out = pd.concat([ada_results], axis=1)
out.columns = ['ada']
out.to_csv('olympics-data/search_engine_results.csv')