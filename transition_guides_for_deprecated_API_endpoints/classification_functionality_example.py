import itertools
from collections import defaultdict

from transformers import GPT2TokenizerFast

import openai

tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")

MAX_TOKENS_LIMIT = 2048


def create_instruction(labels) -> str:
    """
    Construct an instruction for a classification task.
    """
    instruction = f"Please classify a piece of text into the following categories: {', '.join(labels)}."

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


def format_example_fn(x: dict) -> str:
    return "Text: {text}\nCategory: {label}\n---\n".format(
        text=x["text"].replace("\n", " ").strip(),
        label=x["label"].replace("\n", " ").strip(),
    )


def classifications(
    query,
    model,
    search_model="ada",
    examples=None,
    file=None,
    labels=None,
    temperature=0.0,
    logprobs=None,
    max_examples=200,
    logit_bias=None,
    alternative_query=None,
    max_tokens=16,
) -> dict:
    """
    Given a prompt, a question and a list of examples, containing (text, label) pairs,
    it selects top relevant examples to construct a prompt for few-shot classification.

    The constructed prompt for the final completion call:
    ```
    {{ an optional instruction }}

    Text: example 1 text
    Category: example 1 label
    ---
    Text: example 1 text
    Category: example 2 label
    ---
    Text: question
    Category:
    ```

    The returned object has a structure like:
    {
      "label": "Happy",
      "model": "ada",
      "object": "classification",
      "selected_examples": [
        {
            "document": ...,    # document index, same as in search/ results.
            "text": ...,
            "label": ...,
        },
        ...
      ],
    }
    """

    query = query.replace("\n", " ").strip()
    logit_bias = logit_bias if logit_bias else {}
    labels = labels if labels else []

    if file is None and examples is None:
        raise Exception("Please submit at least one of `examples` or `file`.")
    if file is not None and examples is not None:
        raise Exception("Please submit only one of `examples` or `file`.")

    instruction = create_instruction(labels)

    query_for_search = alternative_query if alternative_query is not None else query

    # Extract examples and example labels first.
    if file is not None:
        sorted_doc_infos = semantic_search(
            search_model,
            query_for_search,
            file_id=file,
            max_documents=max_examples,
        )

    else:
        example_prompts = [
            format_example_fn(dict(text=x, label=y)) for x, y in examples
        ]
        n_examples_tokens = [len(tokenizer.encode(x)) for x in example_prompts]

    query_prompt = f"Text: {query}\nCategory:"
    n_instruction_tokens = len(tokenizer.encode(instruction))
    n_query_tokens = len(tokenizer.encode(query_prompt))

    # Except all the required content, how many tokens left for context stuffing.
    leftover_token_len = MAX_TOKENS_LIMIT - (
        n_instruction_tokens + n_query_tokens + max_tokens
    )

    # Process when `examples` are provided but no `file` is provided.
    if examples:
        if (max_examples is None or max_examples >= len(examples)) and sum(
            n_examples_tokens
        ) < leftover_token_len:
            # If the total length of docs is short enough that we can add all examples, no search call.
            selected_indices = list(range(len(examples)))

            sorted_doc_infos = [
                {"document": i, "text": examples[i][0], "label": examples[i][1]}
                for i in selected_indices
            ]

        elif max(n_examples_tokens) + n_query_tokens >= MAX_TOKENS_LIMIT:
            # If the prompt and the longest example together go above the limit:
            total_tokens = max(n_examples_tokens) + n_query_tokens
            raise Exception(
                user_message=f"The longest classification example, query and prompt together contain "
                f"{total_tokens} tokens, above the limit {MAX_TOKENS_LIMIT} for semantic search. "
                f"Please consider shortening your instruction, query or the longest example."
            )

        else:
            # If we can add some context documents but not all of them, we should
            # query search endpoint to rank docs by score.
            sorted_doc_infos = semantic_search(
                search_model,
                query_for_search,
                examples=[{"text": x, "label": y} for x, y in examples],
                max_documents=max_examples,
            )

    # Per label, we have a list of doc id sorted by its relevancy to the query.
    label_to_indices = defaultdict(list)
    for idx, d in enumerate(sorted_doc_infos):
        label_to_indices[d["label"]].append(idx)

    # Do a round robin for each of the different labels, taking the best match for each label.
    label_indices = [label_to_indices[label] for label in labels]
    mixed_indices = [
        i for x in itertools.zip_longest(*label_indices) for i in x if i is not None
    ]
    sorted_doc_infos = [sorted_doc_infos[i] for i in mixed_indices]

    # Try to select as many examples as needed to fit into the context
    context, sorted_doc_infos = select_by_length(
        sorted_doc_infos,
        leftover_token_len,
        lambda_fn=format_example_fn,
    )

    prompt = instruction + context + query_prompt

    completion_params = {
        "engine": model,
        "prompt": prompt,
        "temperature": temperature,
        "logprobs": logprobs,
        "logit_bias": logit_bias,
        "max_tokens": max_tokens,
        "stop": "\n",
        "n": 1,
    }

    completion_resp = openai.Completion.create(
        **completion_params,
    )

    label = completion_resp["choices"][0]["text"]
    label = label.split("\n")[0].strip().lower().capitalize()
    if label not in labels:
        label = "Unknown"

    result = dict(
        # TODO: Add id for object persistence.
        object="classification",
        model=completion_resp["model"],
        label=label,
        completion=completion_resp["id"],
    )

    result["selected_examples"] = sorted_doc_infos

    return result


print(
    classifications(
        query="this is my test",
        model="davinci",
        search_model="ada",
        examples=[
            ["this is my test", "davinci"],
            ["this is other test", "blahblah"],
        ],
        file=None,
        labels=["davinci", "blahblah"],
        temperature=0.1,
        logprobs=0,
        max_examples=200,
        logit_bias=None,
        alternative_query="different test",
        max_tokens=16,
    )
)
