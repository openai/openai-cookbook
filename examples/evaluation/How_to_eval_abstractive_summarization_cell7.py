# function to calculate the Rouge score
def get_rouge_scores(text1, text2):
    rouge = Rouge()
    return rouge.get_scores(text1, text2)


rouge_scores_out = []

# Calculate the ROUGE scores for both summaries using reference
eval_1_rouge = get_rouge_scores(eval_summary_1, ref_summary)
eval_2_rouge = get_rouge_scores(eval_summary_2, ref_summary)

for metric in ["rouge-1", "rouge-2", "rouge-l"]:
    for label in ["F-Score"]:
        eval_1_score = eval_1_rouge[0][metric][label[0].lower()]
        eval_2_score = eval_2_rouge[0][metric][label[0].lower()]

        row = {
            "Metric": f"{metric} ({label})",
            "Summary 1": eval_1_score,
            "Summary 2": eval_2_score,
        }
        rouge_scores_out.append(row)


def highlight_max(s):
    is_max = s == s.max()
    return [
        "background-color: lightgreen" if v else "background-color: white"
        for v in is_max
    ]


rouge_scores_out = (
    pd.DataFrame(rouge_scores_out)
    .set_index("Metric")
    .style.apply(highlight_max, axis=1)
)

rouge_scores_out