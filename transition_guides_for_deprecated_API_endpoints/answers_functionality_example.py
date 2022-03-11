from transformers import GPT2TokenizerFast

import openai

tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")

MAX_TOKENS_LIMIT = 2048
ANSWERS_INSTRUCTION = "Please answer the question according to the above context.\n"
CONTEXT_TEMPLATE = "===\nContext: {context}\n===\n"


def extract_instruction(instruction):
    """
    Extract `instruction` parameter and format it properly.
    If not exist, return empty string.
    """
    if instruction is None:
        return ""

    return f"{instruction.strip()}\n\n"


def semantic_search(
    search_model, query_for_search, file_id=None, max_documents=None, examples=None
):
    """
    :param examples: A list of {"text":...} or {"text": ..., "label": ...}.
    :return:
        a list of semantic search result dict of documents sorted by "score":
        [
            {
                "document": ...,
                "object": "search_result",
                "score": ...,
                "text": ...,
            },
            ...
        ]
    """
    assert (examples is None) ^ (file_id is None)  # xor

    if file_id is not None:
        # This is where you'd do an elastic search call.  Since there isn't an example of this
        # we can query, we'll raise an error.
        # The return value from this would be a list of examples
        raise NotImplementedError()

    # This isn't quite accurate since Search is also being deprecated. See our search guide for more
    # information.

    search_result = openai.Search.create(
        model=search_model,
        documents=[x["text"] for x in examples],
        query=query_for_search,
    )

    info_dict = {d["document"]: d for d in search_result["data"]}
    sorted_doc_ids = sorted(
        info_dict.keys(), key=lambda x: info_dict[x]["score"], reverse=True
    )
    if max_documents:
        sorted_doc_ids = sorted_doc_ids[:max_documents]
    return [info_dict[i] for i in sorted_doc_ids]


def select_by_length(
    sorted_doc_infos,
    max_token_len,
    lambda_fn=None,
):
    """
    Give a list of (document ID, document content in string), we will select as many
    documents as possible as long as the total length does not go above `max_token_len`.

    :param sorted_doc_infos: A list of semantic search result dict of documents sorted by "score".
    :param max_token_len: The maximum token length for selected documents.
    :param lambda_fn: A function that takes in search results dict and output a formatted
        example for context stuffing.
    :return: A tuple of (
        A concatenation of selected documents used as context,
        A list of selected document IDs
    )
    """
    if not sorted_doc_infos:
        return "", []

    selected_indices = []
    total_doc_tokens = 0
    doc_dict = {}
    for i, doc_info in enumerate(sorted_doc_infos):
        doc = lambda_fn(doc_info) if lambda_fn else doc_info["text"]
        n_doc_tokens = len(tokenizer.encode(doc))
        if total_doc_tokens + n_doc_tokens < max_token_len:
            total_doc_tokens += n_doc_tokens
            selected_indices.append(i)
            doc_dict[i] = doc

    # The top ranked documents should go at the end.
    selected_indices = selected_indices[::-1]

    context = "".join([doc_dict[i] for i in selected_indices])
    selected_doc_infos = [sorted_doc_infos[i] for i in selected_indices]
    return context, selected_doc_infos


def answers(
    examples,
    question,
    model,
    examples_context,
    file_id=None,
    documents=None,
    logit_bias=None,
    max_rerank=200,
    max_tokens=16,
    alternative_question=None,
    search_model="ada",
    temperature=0.0,
    logprobs=0,
    stop=None,
    n=1,
):
    """
    Given a prompt, a question, a list of (question, answer) pairs as examples, and
    a list of documents for context, it tries to include all the QA examples and top
    relevant context documents.

    The constructed prompt for the final completion call:
    ```
    Please answer the question according to the above context.

    ===
    Context: {{ the context for example QA pairs. }}
    ===
    Q: example 1 question
    A: example 1 answer
    ---
    Q: example 2 question
    A: example 2 answer
    ===
    Context: {{ a list of relevant documents sorted via search(question, documents) }}
    ===
    Q: question
    A:
    ```

    The returned object has a structure like:
    {
      "answers": [
        "Beijing",
        "Beijing, China"
      ],
      "completion_id": "xxx-xxx",
      "object": "answer",
      "selected_documents": [
        {
            "document": ...,    # document index, same as in search/ results.
            "object": "search_result",
            "text": ...,
        },
        ...
      ],
    }
    """

    examples = examples if examples else []

    example_prompts = [f"Q: {x}\nA: {y}" for x, y in examples]
    prompt = f"Q: {question}\nA:"

    # Append all the QA examples into the prompt.
    if examples_context:
        examples_context = CONTEXT_TEMPLATE.format(context=examples_context)
    instruction = (
        ANSWERS_INSTRUCTION + examples_context + "\n---\n".join(example_prompts) + "\n"
    )

    logit_bias = logit_bias if logit_bias is not None else {}

    if file_id is None and documents is None:
        raise Exception("Please submit at least one of `documents` or `file`.")
    if file_id is not None and documents is not None:
        raise Exception("Please submit only one of `documents` or `file`.")

    instruction = extract_instruction(instruction)

    n_instruction_tokens = len(tokenizer.encode(instruction))
    n_prompt_tokens = len(tokenizer.encode(prompt))
    n_query_tokens = len(tokenizer.encode(question))
    n_context_tokens = len(tokenizer.encode(CONTEXT_TEMPLATE.format(context="")))

    if documents is not None:
        documents = [doc.strip() + " " for doc in documents]
        n_docs_tokens = [len(tokenizer.encode(doc)) for doc in documents]

    # Except all the required content, how many tokens left for context stuffing.
    leftover_token_len = MAX_TOKENS_LIMIT - (
        n_instruction_tokens + n_context_tokens + n_prompt_tokens + max_tokens
    )
    sorted_doc_infos = []

    question_for_search = (
        alternative_question if alternative_question is not None else question
    )
    if file_id is not None:
        search_model_, sorted_doc_infos = semantic_search(
            search_model,
            question_for_search,
            file_id=file_id,
            max_documents=max_rerank,
        )

    elif len(documents) == 0:
        # If no context document is provided, do nothing.
        pass

    elif min(n_docs_tokens) >= leftover_token_len:
        # If there is no room for adding any context doc.
        pass

    elif (max_rerank is None or max_rerank >= len(documents)) and sum(
        n_docs_tokens
    ) < leftover_token_len:
        # If the total length of docs is short enough to be added all.
        selected_indices = list(range(len(documents)))

        sorted_doc_infos = [
            {"document": i, "text": documents[i]} for i in selected_indices
        ]

    elif n_query_tokens + max(n_docs_tokens) >= MAX_TOKENS_LIMIT:
        # If the prompt and the longest document together go above the limit.
        total_tokens = n_query_tokens + max(n_docs_tokens)
        raise Exception(
            f"The longest document and prompt pair together contains {total_tokens} "
            f"tokens, above the limit {MAX_TOKENS_LIMIT} for semantic search. Please consider "
            f"shortening the prompt or the longest document."
        )

    else:
        # If we can add some context documents but not all of them, we should
        # query search endpoint to rank docs by score.
        sorted_doc_infos = semantic_search(
            search_model,
            question_for_search,
            examples=[{"text": doc} for doc in documents],
            max_documents=max_rerank,
        )

    # Select documents w.r.t. the context length limitation.
    context, sorted_doc_infos = select_by_length(
        sorted_doc_infos,
        leftover_token_len,
        lambda_fn=lambda x: x["text"].strip() + " ",
    )

    # Add instruction before the context and the prompt after the context.
    if context:
        context = CONTEXT_TEMPLATE.format(context=context.strip())
    full_prompt = instruction + context + prompt

    completion_result = openai.Completion.create(
        engine=model,
        prompt=full_prompt,
        logit_bias=logit_bias,
        temperature=temperature,
        n=n,
        max_tokens=max_tokens,
        stop=stop,
        logprobs=logprobs,
    )

    completion_result["selected_documents"] = sorted_doc_infos

    result = dict(
        object="answer",
        selected_documents=completion_result.pop("selected_documents"),
        completion=completion_result["id"],
    )

    result["answers"] = [
        item["text"].replace("A:", "").split("Q:")[0].strip()
        for item in completion_result["choices"]
    ]

    return result


print(
    answers(
        examples=[
            ["What is the capital of Washington", "Olympia"],
            ["What is the capital of Oregon", "Salem"],
        ],
        question="What is the capital of China?",
        examples_context="I am a bot that names country capitals",
        documents=["I am a bot that names country capitals"],
        model="davinci",
        search_model="ada",
        alternative_question="different test",
        max_tokens=16,
        stop=["\n\n"],
    )
)
