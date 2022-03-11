from typing import List, Union

from smokey import Smokey

import openai


def get_candidates(
    prompt: str,
    stop: List[str],
    temperature: float,
    priming_prefix: str,
    engine: str,
    n: int = 5,
) -> List[str]:
    """
    Generate N candidate completions based on the prompt, generated with a specific temperature.

    :param prompt: The prompt to start the conversation with.
    :param stop: A list of tokens that indicate the end of the generation.
    :param temperature: The temperature of the generation.
    :param priming_prefix: The prefix to use for the priming.
    :param engine: The engine to use for the generation.
    :param n: The number of completions to generate.
    :return: A list of completions.
    """
    response = openai.Completion.create(
        engine=engine,
        prompt=prompt,
        temperature=temperature,
        max_tokens=150,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stop=stop,
        n=n,
    )
    responses = [priming_prefix + choice.text for choice in response.choices]
    return responses


def rindex(lst: List, value: str) -> int:
    """
    Return the index of the last occurence of a value in a list.

    :param lst: The list to search in.
    :param value: The value to search for.
    :return: The index of the last occurence of the value.
    """
    try:
        return len(lst) - lst[::-1].index(value) - 1
    except ValueError:
        raise ValueError(f"Answer start token `{value}` not found in the eval template")


def eval_candidate(
    candidate_answer: str,
    original_instruction: str,
    eval_template: str,
    answer_start_token: str,
    engine: str,
) -> float:
    """
    Evaluate a candidate answer by calculating the average log probability
    of the original instruction, given the candidate answer with a specific
    evaluation template, aimed at reconstructing the original instruction.

    :param candidate_answer: The candidate answer to evaluate.
    :param original_instruction: The original instruction.
    :param eval_template: The template to use for the evaluation.
    :param answer_start_token: The token to use to indicate the start of the answer.
    :param engine: The engine to use for the evaluation.
    :return: The evaluation of the candidate answer.
    """
    response = openai.Completion.create(
        engine=engine,
        prompt=eval_template.format(candidate_answer, original_instruction),
        temperature=0,
        max_tokens=0,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        logprobs=1,
        echo=True,
    )

    answer_start = rindex(
        response["choices"][0]["logprobs"]["tokens"], answer_start_token
    )
    logprobs = response["choices"][0]["logprobs"]["token_logprobs"][answer_start + 1 :]
    return sum(logprobs) / len(logprobs)


def backtranslation(
    prompt_template: str,
    additional_info: str,
    instruction: str,
    eval_template: str,
    priming_prefix: str = "SELECT",
    stop1: List[str] = ["#", ";"],
    answer_start_token: str = "--",
    n: int = 5,
    temperature: float = 0.5,
    return_all_results: bool = False,
    engine: str = "davinci-codex",
) -> Union[str, List[str, float]]:
    """
    Generate a number of SQL queries given a natural language instruction,
    and pick the best one based on the average log probability of explaining the
    candidate SQL query with the exact original instruction, when prompted for
    a natural language explanation of the candidate SQL query.

    :param prompt_template: The template to use for the prompt to generate SQL.
    :param additional_info: Additional information to include in the prompt
                            (SQL Tables, and their properties).
    :param instruction: The instruction in natural language.
    :param eval_template: The template to use for the evaluation.
    :param priming_prefix: The prefix to use for the priming of the SQL query.
    :param stop1: A list of tokens that indicate the end of the generation.
    :param answer_start_token: The token to use to indicate the start of the
                               natural answer.
    :param n: The number of candidates to generate.
    :param temperature: The temperature of the generation.
    :param return_all_results: Whether to return all results or just the best one.
    :param engine: The engine to use for the generation and evaluation.
    :return: The best SQL query, or a list of all scored generated SQL queries.
    """
    prompt_template = prompt_template.format(
        additional_info, instruction, priming_prefix
    )

    candidates = []
    responses = get_candidates(
        prompt_template, stop1, temperature, priming_prefix, engine=engine, n=n
    )
    for i in range(n):
        quality = eval_candidate(
            responses[i],
            instruction,
            eval_template,
            answer_start_token,
            engine=engine,
        )
        candidates.append((responses[i], quality))

    candidates.sort(key=lambda x: x[1], reverse=True)
    if return_all_results:
        return candidates
    return candidates[0][0]


def main(
    nl_query: str = "Return the name of each department that had more than 10 employees in June 2021",
    eval_template: str = "{};\n-- Explanation of the above query in human readable format\n-- {}",
    table_definitions: str = "# Employee(id, name, department_id)\n# Department(id, name, address)\n# Salary_Payments(id, employee_id, amount, date)\n",
    prompt_template: str = "### Postgres SQL tables, with their properties:\n#\n{}#\n### {}\n{}",
    n: int = 3,
    temperature: float = 0.3,
    engine: str = "davinci-codex",
):
    """
    Generate a number of SQL queries given a natural language instruction,
    and pick the best one based on the highest backtranslation score.

    :param nl_query: The natural language query.
    :param eval_template: The template to use for the evaluation.
    :param table_definitions: The definitions of the tables used in the query.
    :param prompt_template: The template to use for the prompt to generate SQL.
    :param n: The number of candidates to generate.
    :param temperature: The temperature of the generation.
    :param engine: The engine to use for the generation and evaluation.
    :return: The best SQL query, or a list of all scored generated SQL queries.
    """

    result = backtranslation(
        prompt_template,
        table_definitions,
        nl_query,
        eval_template,
        priming_prefix="SELECT",
        temperature=temperature,
        n=n,
        engine=engine,
    )
    print(result)


if __name__ == "__main__":
    Smokey(main)
