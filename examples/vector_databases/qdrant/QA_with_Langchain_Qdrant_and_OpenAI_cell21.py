for question in selected_questions:
    print(">", question)
    print(qa.run(question), end="\n\n")