correct = 0
for e in eval_data:
  if e[1].lower() == e[2]["content"].lower():
    correct+=1

accuracy = correct / len(eval_data)

print(f"Accuracy is {accuracy}")
wandb.log({"eval/accuracy": accuracy})
wandb.summary["eval/accuracy"] = accuracy