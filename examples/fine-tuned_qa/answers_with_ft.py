import argparse

import openai


def create_context(
    question, search_file_id, max_len=1800, search_model="ada", max_rerank=10
):
    """
    Create a context for a question by finding the most similar context from the search file.
    :param question: The question
    :param search_file_id: The file id of the search file
    :param max_len: The maximum length of the returned context (in tokens)
    :param search_model: The search model to use
    :param max_rerank: The maximum number of reranking
    :return: The context
    """
    results = openai.Engine(search_model).search(
        search_model=search_model,
        query=question,
        max_rerank=max_rerank,
        file=search_file_id,
        return_metadata=True,
    )
    returns = []
    cur_len = 0
    for result in results["data"]:
        cur_len += int(result["metadata"]) + 4
        if cur_len > max_len:
            break
        returns.append(result["text"])
    return "\n\n###\n\n".join(returns)


def answer_question(
    search_file_id="<SEARCH_FILE_ID>",
    fine_tuned_qa_model="<FT_QA_MODEL_ID>",
    question="Which country won the European Football championship in 2021?",
    max_len=1800,
    search_model="ada",
    max_rerank=10,
    debug=False,
    stop_sequence=["\n", "."],
    max_tokens=100,
):
    """
    Answer a question based on the most similar context from the search file, using your fine-tuned model.
    :param question: The question
    :param fine_tuned_qa_model: The fine tuned QA model
    :param search_file_id: The file id of the search file
    :param max_len: The maximum length of the returned context (in tokens)
    :param search_model: The search model to use
    :param max_rerank: The maximum number of reranking
    :param debug: Whether to output debug information
    :param stop_sequence: The stop sequence for Q&A model
    :param max_tokens: The maximum number of tokens to return
    :return: The answer
    """
    context = create_context(
        question,
        search_file_id,
        max_len=max_len,
        search_model=search_model,
        max_rerank=max_rerank,
    )
    if debug:
        print("Context:\n" + context)
        print("\n\n")
    try:
        # fine-tuned models requires model parameter, whereas other models require engine parameter
        model_param = (
            {"model": fine_tuned_qa_model}
            if ":" in fine_tuned_qa_model
            and fine_tuned_qa_model.split(":")[1].startswith("ft")
            else {"engine": fine_tuned_qa_model}
        )
        response = openai.Completion.create(
            prompt=f"Answer the question based on the context below\n\nText: {context}\n\n---\n\nQuestion: {question}\nAnswer:",
            temperature=0,
            max_tokens=max_tokens,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            stop=stop_sequence,
            **model_param,
        )
        return response["choices"][0]["text"]
    except Exception as e:
        print(e)
        return ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rudimentary functionality of the answers endpoint with a fine-tuned Q&A model.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--search_file_id", help="Search file id", required=True, type=str
    )
    parser.add_argument(
        "--fine_tuned_qa_model", help="Fine-tuned QA model id", required=True, type=str
    )
    parser.add_argument(
        "--question", help="Question to answer", required=True, type=str
    )
    parser.add_argument(
        "--max_len",
        help="Maximum length of the returned context (in tokens)",
        default=1800,
        type=int,
    )
    parser.add_argument(
        "--search_model", help="Search model to use", default="ada", type=str
    )
    parser.add_argument(
        "--max_rerank",
        help="Maximum number of reranking for the search",
        default=10,
        type=int,
    )
    parser.add_argument(
        "--debug", help="Print debug information (context used)", action="store_true"
    )
    parser.add_argument(
        "--stop_sequence",
        help="Stop sequences for the Q&A model",
        default=["\n", "."],
        nargs="+",
        type=str,
    )
    parser.add_argument(
        "--max_tokens",
        help="Maximum number of tokens to return",
        default=100,
        type=int,
    )
    args = parser.parse_args()
    response = answer_question(
        search_file_id=args.search_file_id,
        fine_tuned_qa_model=args.fine_tuned_qa_model,
        question=args.question,
        max_len=args.max_len,
        search_model=args.search_model,
        max_rerank=args.max_rerank,
        debug=args.debug,
        stop_sequence=args.stop_sequence,
        max_tokens=args.max_tokens,
    )
    print(f"Answer:{response}")
