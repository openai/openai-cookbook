from typing import List, Union
from smokey import Smokey
import openai

def get_candidates(prompt: str, stop: List[str], temperature: float, priming_prefix: str, engine: str, n: int = 5) -> List[str]:
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
    return [priming_prefix + choice.text for choice in response.choices]

def rindex(lst: List, value: str) -> int:
    try:
        return len(lst) - lst[::-1].index(value) - 1
    except ValueError:
        raise ValueError(f"Answer start token `{value}` not found in the eval template")

def eval_candidate(candidate_answer: str, original_instruction: str, eval_template: str, answer_start_token: str, engine: str) -> float:
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
    answer_start = rindex(response["choices"][0]["logprobs"]["tokens"], answer_start_token)
    logprobs = response["choices"][0]["logprobs"]["token_logprobs"][answer_start + 1 :]
    return sum(logprobs) / len(logprobs)

def backtranslation(prompt_template: str, additional_info: str, instruction: str, eval_template: str, priming_prefix: str = "SELECT", stop1: List[str] = ["#", ";"], answer_start_token: str = "--", n: int = 5, temperature: float = 0.5, return_all_results: bool = False, engine: str = "davinci-codex") -> Union[str, List[str, float]]:
    prompt_template = prompt_template.format(additional_info, instruction, priming_prefix)
    candidates = []
    responses = get_candidates(prompt_template, stop1, temperature, priming_prefix, engine=engine, n=n)
    for i in range(n):
        quality = eval_candidate(responses[i], instruction, eval_template, answer_start_token, engine=engine)
        candidates.append((responses[i], quality))
    candidates.sort(key=lambda x: x[1], reverse=True)
    if return_all_results:
        return candidates
    return candidates[0][0]

def main(nl_query: str = "Return the name of each department that had more than 10 employees in June 2021", eval_template: str = "{};\n-- Explanation of the above query in human readable format\n-- {}", table_definitions: str = "# Employee(id, name, department_id)\n# Department(id, name, address)\n# Salary_Payments(id, employee_id, amount, date)\n", prompt_template: str = "### Postgres SQL tables, with their properties:\n#\n{}#\n### {}\n{}", n: int = 3, temperature: float = 0.3, engine: str = "davinci-codex"):
    result = backtranslation(prompt_template, table_definitions, nl_query, eval_template, priming_prefix="SELECT", temperature=temperature, n=n, engine=engine)
    print(result)

if __name__ == "__main__":
    Smokey(main)
