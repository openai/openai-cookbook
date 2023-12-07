import time
for question in selected_questions:
    print(">", question)
    print(qa.run(question), end="\n\n")
    # wait 20seconds because of the rate limit
    time.sleep(20)