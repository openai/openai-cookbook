def get_mock_response_from_user_multiple_choice():
    return "a"


def get_mock_response_from_user_free_response():
    return "I don't know."


def display_quiz(title, questions):
    print("Quiz:", title)
    print()
    responses = []

    for q in questions:
        print(q["question_text"])
        response = ""

        # If multiple choice, print options
        if q["question_type"] == "MULTIPLE_CHOICE":
            for i, choice in enumerate(q["choices"]):
                print(f"{i}. {choice}")
            response = get_mock_response_from_user_multiple_choice()

        # Otherwise, just get response
        elif q["question_type"] == "FREE_RESPONSE":
            response = get_mock_response_from_user_free_response()

        responses.append(response)
        print()

    return responses