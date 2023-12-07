# imports needed to run the code in this notebook
import ast  # used for detecting whether generated Python code is valid
from openai import OpenAI

client = OpenAI()  # used for calling the OpenAI API

# example of a function that uses a multi-step prompt to write unit tests
def unit_test_from_function(
    function_to_test: str,  # Python function to test, as a string
    unit_test_package: str = "pytest",  # unit testing package; use the name as it appears in the import statement
    approx_min_cases_to_cover: int = 7,  # minimum number of test case categories to cover (approximate)
    print_text: bool = False,  # optionally prints text; helpful for understanding the function & debugging
    text_model: str = "text-davinci-002",  # model used to generate text plans in steps 1, 2, and 2b
    code_model: str = "code-davinci-002",  # if you don't have access to code models, you can use text models here instead
    max_tokens: int = 1000,  # can set this high, as generations should be stopped earlier by stop sequences
    temperature: float = 0.4,  # temperature = 0 can sometimes get stuck in repetitive loops, so we use 0.4
    reruns_if_fail: int = 1,  # if the output code cannot be parsed, this will re-run the function up to N times
) -> str:
    """Outputs a unit test for a given Python function, using a 3-step GPT-3 prompt."""

    # Step 1: Generate an explanation of the function

    # create a markdown-formatted prompt that asks GPT-3 to complete an explanation of the function, formatted as a bullet list
    prompt_to_explain_the_function = f"""# How to write great unit tests with {unit_test_package}

In this advanced tutorial for experts, we'll use Python 3.9 and `{unit_test_package}` to write a suite of unit tests to verify the behavior of the following function.
```python
{function_to_test}
```

Before writing any unit tests, let's review what each element of the function is doing exactly and what the author's intentions may have been.
- First,"""
    if print_text:
        text_color_prefix = "\033[30m"  # black; if you read against a dark background \033[97m is white
        print(text_color_prefix + prompt_to_explain_the_function, end="")  # end='' prevents a newline from being printed

    # send the prompt to the API, using \n\n as a stop sequence to stop at the end of the bullet list
    explanation_response = client.completions.create(model=text_model,
    prompt=prompt_to_explain_the_function,
    stop=["\n\n", "\n\t\n", "\n    \n"],
    max_tokens=max_tokens,
    temperature=temperature,
    stream=True)
    explanation_completion = ""
    if print_text:
        completion_color_prefix = "\033[92m"  # green
        print(completion_color_prefix, end="")
    for event in explanation_response:
        event_text = event["choices"][0]["text"]
        explanation_completion += event_text
        if print_text:
            print(event_text, end="")

    # Step 2: Generate a plan to write a unit test

    # create a markdown-formatted prompt that asks GPT-3 to complete a plan for writing unit tests, formatted as a bullet list
    prompt_to_explain_a_plan = f"""
    
A good unit test suite should aim to:
- Test the function's behavior for a wide range of possible inputs
- Test edge cases that the author may not have foreseen
- Take advantage of the features of `{unit_test_package}` to make the tests easy to write and maintain
- Be easy to read and understand, with clean code and descriptive names
- Be deterministic, so that the tests always pass or fail in the same way

`{unit_test_package}` has many convenient features that make it easy to write and maintain unit tests. We'll use them to write unit tests for the function above.

For this particular function, we'll want our unit tests to handle the following diverse scenarios (and under each scenario, we include a few examples as sub-bullets):
-"""
    if print_text:
        print(text_color_prefix + prompt_to_explain_a_plan, end="")

    # append this planning prompt to the results from step 1
    prior_text = prompt_to_explain_the_function + explanation_completion
    full_plan_prompt = prior_text + prompt_to_explain_a_plan

    # send the prompt to the API, using \n\n as a stop sequence to stop at the end of the bullet list
    plan_response = client.completions.create(model=text_model,
    prompt=full_plan_prompt,
    stop=["\n\n", "\n\t\n", "\n    \n"],
    max_tokens=max_tokens,
    temperature=temperature,
    stream=True)
    plan_completion = ""
    if print_text:
        print(completion_color_prefix, end="")
    for event in plan_response:
        event_text = event["choices"][0]["text"]
        plan_completion += event_text
        if print_text:
            print(event_text, end="")

    # Step 2b: If the plan is short, ask GPT-3 to elaborate further
    # this counts top-level bullets (e.g., categories), but not sub-bullets (e.g., test cases)
    elaboration_needed = plan_completion.count("\n-") +1 < approx_min_cases_to_cover  # adds 1 because the first bullet is not counted
    if elaboration_needed:
        prompt_to_elaborate_on_the_plan = f"""

In addition to the scenarios above, we'll also want to make sure we don't forget to test rare or unexpected edge cases (and under each edge case, we include a few examples as sub-bullets):
-"""
        if print_text:
            print(text_color_prefix + prompt_to_elaborate_on_the_plan, end="")

        # append this elaboration prompt to the results from step 2
        prior_text = full_plan_prompt + plan_completion
        full_elaboration_prompt = prior_text + prompt_to_elaborate_on_the_plan

        # send the prompt to the API, using \n\n as a stop sequence to stop at the end of the bullet list
        elaboration_response = client.completions.create(model=text_model,
        prompt=full_elaboration_prompt,
        stop=["\n\n", "\n\t\n", "\n    \n"],
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True)
        elaboration_completion = ""
        if print_text:
            print(completion_color_prefix, end="")
        for event in elaboration_response:
            event_text = event["choices"][0]["text"]
            elaboration_completion += event_text
            if print_text:
                print(event_text, end="")

    # Step 3: Generate the unit test

    # create a markdown-formatted prompt that asks GPT-3 to complete a unit test
    starter_comment = ""
    if unit_test_package == "pytest":
        starter_comment = "Below, each test case is represented by a tuple passed to the @pytest.mark.parametrize decorator"
    prompt_to_generate_the_unit_test = f"""

Before going into the individual tests, let's first look at the complete suite of unit tests as a cohesive whole. We've added helpful comments to explain what each line does.
```python
import {unit_test_package}  # used for our unit tests

{function_to_test}

#{starter_comment}"""
    if print_text:
        print(text_color_prefix + prompt_to_generate_the_unit_test, end="")

    # append this unit test prompt to the results from step 3
    if elaboration_needed:
        prior_text = full_elaboration_prompt + elaboration_completion
    else:
        prior_text = full_plan_prompt + plan_completion
    full_unit_test_prompt = prior_text + prompt_to_generate_the_unit_test

    # send the prompt to the API, using ``` as a stop sequence to stop at the end of the code block
    unit_test_response = client.completions.create(model=code_model,
    prompt=full_unit_test_prompt,
    stop="```",
    max_tokens=max_tokens,
    temperature=temperature,
    stream=True)
    unit_test_completion = ""
    if print_text:
        print(completion_color_prefix, end="")
    for event in unit_test_response:
        event_text = event["choices"][0]["text"]
        unit_test_completion += event_text
        if print_text:
            print(event_text, end="")

    # check the output for errors
    code_start_index = prompt_to_generate_the_unit_test.find("```python\n") + len("```python\n")
    code_output = prompt_to_generate_the_unit_test[code_start_index:] + unit_test_completion
    try:
        ast.parse(code_output)
    except SyntaxError as e:
        print(f"Syntax error in generated code: {e}")
        if reruns_if_fail > 0:
            print("Rerunning...")
            return unit_test_from_function(
                function_to_test=function_to_test,
                unit_test_package=unit_test_package,
                approx_min_cases_to_cover=approx_min_cases_to_cover,
                print_text=print_text,
                text_model=text_model,
                code_model=code_model,
                max_tokens=max_tokens,
                temperature=temperature,
                reruns_if_fail=reruns_if_fail-1,  # decrement rerun counter when calling again
            )

    # return the unit test as a string
    return unit_test_completion
