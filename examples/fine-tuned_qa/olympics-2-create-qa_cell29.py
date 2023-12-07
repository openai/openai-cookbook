outside_200 = (out_expanded['rank'] == -1).mean()
print(f"{outside_200*100:.1f}% of relevant paragraphs are not retrieved within the first 200 results")