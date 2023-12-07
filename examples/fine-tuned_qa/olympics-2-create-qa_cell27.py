within_2k = (out_expanded.tokens < 2000).mean()
print(f"{within_2k*100:.1f}% of relevant paragraphs are retrieved within the first 2k tokens")