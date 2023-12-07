# imports needed to run the code in this notebook
import ast  # used for detecting whether generated Python code is valid
from openai import OpenAI

client = OpenAI()  # used for calling the OpenAI API

color_prefix_by_role = {
    "system": "\033[0m",  # gray
    "user": "\033[0m",  # gray
    "assistant": "\033[92m",  # green
}


def print_messages(messages, color_prefix_by_role=color_prefix_by_role) -> None:
    """Prints messages sent to or from GPT."""
    for message in messages:
        role = message["role"]
        color_prefix = color_prefix_by_role[role]
        content = message["content"]
        print(f"{color_prefix}\n[{role}]\n{content}")


def print_message_delta(delta, color_prefix_by_role=color_prefix_by_role) -> None:
    """Prints a chunk of messages streamed back from GPT."""
    if "role" in delta:
        role = delta["role"]
        color_prefix = color_prefix_by_role[role]
        print(f"{color_prefix}\n[{role}]\n", end="")
    elif "content" in delta:
        content = delta["content"]
        print(content, end="")
    else:
        pass


# example of a function that uses a multi-step prompt to write unit tests
def unit_tests_from_function(
    function_to_test: str,  # Python function to test, as a string
    unit_test_package: str = "pytest",  # unit testing package; use the name as it appears in the import statement
    approx_min_cases_to_cover: int = 7,  # minimum number of test case categories to cover (approximate)
    print_text: bool = False,  # optionally prints text; helpful for understanding the function & debugging
    explain_model: str = "gpt-3.5-turbo",  # model used to generate text plans in step 1
    plan_model: str = "gpt-3.5-turbo",  # model used to generate text plans in steps 2 and 2b
    execute_model: str = "gpt-3.5-turbo",  # model used to generate code in step 3
    temperature: float = 0.4,  # temperature = 0 can sometimes get stuck in repetitive loops, so we use 0.4
    reruns_if_fail: int = 1,  # if the output code cannot be parsed, this will re-run the function up to N times
) -> str:
    """Returns a unit test for a given Python function, using a 3-step GPT prompt."""

    # Step 1: Generate an explanation of the function

    # create a markdown-formatted message that asks GPT to explain the function, formatted as a bullet list
    explain_system_message = {
        "role": "system",
        "content": "You are a world-class Python developer with an eagle eye for unintended bugs and edge cases. You carefully explain code with great detail and accuracy. You organize your explanations in markdown-formatted, bulleted lists.",
    }
    explain_user_message = {
        "role": "user",
        "content": f"""Please explain the following Python function. Review what each element of the function is doing precisely and what the author's intentions may have been. Organize your explanation as a markdown-formatted, bulleted list.

```python
{function_to_test}
```""",
    }
    explain_messages = [explain_system_message, explain_user_message]
    if print_text:
        print_messages(explain_messages)

    explanation_response = client.chat.completions.create(model=explain_model,
    messages=explain_messages,
    temperature=temperature,
    stream=True)
    explanation = ""
    for chunk in explanation_response:
        delta = chunk["choices"][0]["delta"]
        if print_text:
            print_message_delta(delta)
        if "content" in delta:
            explanation += delta["content"]
    explain_assistant_message = {"role": "assistant", "content": explanation}

    # Step 2: Generate a plan to write a unit test

    # Asks GPT to plan out cases the units tests should cover, formatted as a bullet list
    plan_user_message = {
        "role": "user",
        "content": f"""A good unit test suite should aim to:
- Test the function's behavior for a wide range of possible inputs
- Test edge cases that the author may not have foreseen
- Take advantage of the features of `{unit_test_package}` to make the tests easy to write and maintain
- Be easy to read and understand, with clean code and descriptive names
- Be deterministic, so that the tests always pass or fail in the same way

To help unit test the function above, list diverse scenarios that the function should be able to handle (and under each scenario, include a few examples as sub-bullets).""",
    }
    plan_messages = [
        explain_system_message,
        explain_user_message,
        explain_assistant_message,
        plan_user_message,
    ]
    if print_text:
        print_messages([plan_user_message])
    plan_response = client.chat.completions.create(model=plan_model,
    messages=plan_messages,
    temperature=temperature,
    stream=True)
    plan = ""
    for chunk in plan_response:
        delta = chunk["choices"][0]["delta"]
        if print_text:
            print_message_delta(delta)
        if "content" in delta:
            plan += delta["content"]
    plan_assistant_message = {"role": "assistant", "content": plan}

    # Step 2b: If the plan is short, ask GPT to elaborate further
    # this counts top-level bullets (e.g., categories), but not sub-bullets (e.g., test cases)
    num_bullets = max(plan.count("\n-"), plan.count("\n*"))
    elaboration_needed = num_bullets < approx_min_cases_to_cover
    if elaboration_needed:
        elaboration_user_message = {
            "role": "user",
            "content": f"""In addition to those scenarios above, list a few rare or unexpected edge cases (and as before, under each edge case, include a few examples as sub-bullets).""",
        }
        elaboration_messages = [
            explain_system_message,
            explain_user_message,
            explain_assistant_message,
            plan_user_message,
            plan_assistant_message,
            elaboration_user_message,
        ]
        if print_text:
            print_messages([elaboration_user_message])
        elaboration_response = client.chat.completions.create(model=plan_model,
        messages=elaboration_messages,
        temperature=temperature,
        stream=True)
        elaboration = ""
        for chunk in elaboration_response:
            delta = chunk["choices"][0]["delta"]
            if print_text:
                print_message_delta(delta)
            if "content" in delta:
                elaboration += delta["content"]
        elaboration_assistant_message = {"role": "assistant", "content": elaboration}

    # Step 3: Generate the unit test

    # create a markdown-formatted prompt that asks GPT to complete a unit test
    package_comment = ""
    if unit_test_package == "pytest":
        package_comment = "# below, each test case is represented by a tuple passed to the @pytest.mark.parametrize decorator"
    execute_system_message = {
        "role": "system",
        "content": "You are a world-class Python developer with an eagle eye for unintended bugs and edge cases. You write careful, accurate unit tests. When asked to reply only with code, you write all of your code in a single block.",
    }
    execute_user_message = {
        "role": "user",
        "content": f"""Using Python and the `{unit_test_package}` package, write a suite of unit tests for the function, following the cases above. Include helpful comments to explain each line. Reply only with code, formatted as follows:

```python
# imports
import {unit_test_package}  # used for our unit tests
{{insert other imports as needed}}

# function to test
{function_to_test}

# unit tests
{package_comment}
{{insert unit test code here}}
```""",
    }
    execute_messages = [
        execute_system_message,
        explain_user_message,
        explain_assistant_message,
        plan_user_message,
        plan_assistant_message,
    ]
    if elaboration_needed:
        execute_messages += [elaboration_user_message, elaboration_assistant_message]
    execute_messages += [execute_user_message]
    if print_text:
        print_messages([execute_system_message, execute_user_message])

    execute_response = client.chat.completions.create(model=execute_model,
    messages=execute_messages,
    temperature=temperature,
    stream=True)
    execution = ""
    for chunk in execute_response:
        delta = chunk["choices"][0]["delta"]
        if print_text:
            print_message_delta(delta)
        if "content" in delta:
            execution += delta["content"]

    # check the output for errors
    code = execution.split("```python")[1].split("```")[0].strip()
    try:
        ast.parse(code)
    except SyntaxError as e:
        print(f"Syntax error in generated code: {e}")
        if reruns_if_fail > 0:
            print("Rerunning...")
            return unit_tests_from_function(
                function_to_test=function_to_test,
                unit_test_package=unit_test_package,
                approx_min_cases_to_cover=approx_min_cases_to_cover,
                print_text=print_text,
                explain_model=explain_model,
                plan_model=plan_model,
                execute_model=execute_model,
                temperature=temperature,
                reruns_if_fail=reruns_if_fail
                - 1,  # decrement rerun counter when calling again
            )

    # return the unit test as a string
    return code
