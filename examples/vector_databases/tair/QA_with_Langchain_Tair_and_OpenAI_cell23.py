random.seed(41)
for question in random.choices(questions, k=5):
    print(">", question)
    print(custom_qa.run(question), end="\n\n")
    # wait 20seconds because of the rate limit
    time.sleep(20)