gpt_with_context_evaluation = assess_claims_with_context(claims, claim_query_result['documents'])
confusion_matrix(gpt_with_context_evaluation, groundtruth)