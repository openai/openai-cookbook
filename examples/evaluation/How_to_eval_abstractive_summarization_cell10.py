# Instantiate the BERTScorer object for English language
scorer = BERTScorer(lang="en")

# Calculate BERTScore for the summary 1 against the excerpt
# P1, R1, F1_1 represent Precision, Recall, and F1 Score respectively
P1, R1, F1_1 = scorer.score([eval_summary_1], [ref_summary])

# Calculate BERTScore for summary 2 against the excerpt
# P2, R2, F2_2 represent Precision, Recall, and F1 Score respectively
P2, R2, F2_2 = scorer.score([eval_summary_2], [ref_summary])

print("Summary 1 F1 Score:", F1_1.tolist()[0])
print("Summary 2 F1 Score:", F2_2.tolist()[0])