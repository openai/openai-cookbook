# Let's get relevancy score

relevancy_score = sum(result.passing for result in eval_results['faithfulness']) / len(eval_results['relevancy'])

relevancy_score
