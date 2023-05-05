# imports needed to run the code in this notebook
import ast
import code  # used for detecting whether generated Python code is valid
import openai  # used for calling the OpenAI API


# example of a function that uses a multi-step prompt to write unit tests
def unit_test_from_function(
    function_to_test: str,  # Python function to test, as a string
    unit_test_package: str = "pytest",  # unit testing package; use the name as it appears in the import statement
    approx_min_cases_to_cover: int = 7,  # minimum number of test case categories to cover (approximate)
    print_text: bool = False,  # optionally prints text; helpful for understanding the function & debugging
    engine: str = "GPT4",  # engine used to generate text plans in steps 1, 2, and 2b
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
        print(
            text_color_prefix + prompt_to_explain_the_function, end=""
        )  # end='' prevents a newline from being printed

    # send the prompt to the API, using \n\n as a stop sequence to stop at the end of the bullet list
    explanation_response = openai.ChatCompletion.create(
        engine=engine,
        messages=[{
            "role":"system",
            "content": prompt_to_explain_the_function
        }],
        # stop=["\n\n", "\n\t\n", "\n    \n"],
        # max_tokens=max_tokens,
        # temperature=temperature,
        # stream=True,
    )
    # explanation_completion = ""
    if print_text:
        completion_color_prefix = "\033[92m"  # green
        print(completion_color_prefix, end="")
    explanation_completion = explanation_response.choices[0].message.content
    if print_text:
        print(explanation_completion, end="")

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
    plan_response = openai.ChatCompletion.create(
        engine=engine,
        messages=[{
            "role":"system",
            "content": full_plan_prompt
        }],
        # stop=["\n\n", "\n\t\n", "\n    \n"],
        # max_tokens=max_tokens,
        # temperature=temperature,
        # stream=True,
    )
    # plan_completion = ""
    if print_text:
        print(completion_color_prefix, end="")
    plan_completion = plan_response.choices[0].message.content
    if print_text:
        print(plan_completion, end="")

    # Step 2b: If the plan is short, ask GPT-3 to elaborate further
    # this counts top-level bullets (e.g., categories), but not sub-bullets (e.g., test cases)
    elaboration_needed = (
        plan_completion.count("\n-") + 1 < approx_min_cases_to_cover
    )  # adds 1 because the first bullet is not counted
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
        elaboration_response = openai.ChatCompletion.create(
            engine=engine,
            messages=[{
                "role":"system",
                "content": full_elaboration_prompt
            }],
            # stop=["\n\n", "\n\t\n", "\n    \n"],
            # max_tokens=max_tokens,
            # temperature=temperature,
            # stream=True,
        )
        # elaboration_completion = ""
        if print_text:
            print(completion_color_prefix, end="")
        elaboration_completion = elaboration_response.choices[0].message.content
        if print_text:
            print(elaboration_completion, end="")

    # Step 3: Generate the unit test

    # create a markdown-formatted prompt that asks GPT-3 to complete a unit test
    starter_comment = ""
    if unit_test_package == "pytest":
        starter_comment = (
            "Below, each test case is represented by a tuple passed to the @pytest.mark.parametrize decorator"
        )
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
    unit_test_response = openai.ChatCompletion.create(
        engine=engine,
        messages=[{
            "role":"system",
            "content": full_unit_test_prompt
        }],
        # stop="```",
        # max_tokens=max_tokens,
        # temperature=temperature,
        # stream=True,
    )
    # unit_test_completion = ""
    if print_text:
        print(completion_color_prefix, end="")
    unit_test_completion = unit_test_response.choices[0].message.content
    if print_text:
        print(unit_test_completion, end="")

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
                engine=engine,
                max_tokens=max_tokens,
                temperature=temperature,
                reruns_if_fail=reruns_if_fail - 1,  # decrement rerun counter when calling again
            )

    # return the unit test as a string
    return unit_test_completion


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    openai.api_version = "2023-03-15-preview"
    openai.api_base = "https://aoaihackathon.openai.azure.com/"
    openai.api_type = "azure"
    openai.api_key = os.getenv("OPENAI_API_KEY")

    engine = "GPT4"
    # model = "gpt-4"

    functions_file = "dq_check_short.py"
    with open(functions_file) as f:
        codes = f.read()

    # response = openai.ChatCompletion.create(
    #     engine=engine,
    #     # model=model,
    #     messages=[{"role": "system", "content": "Can you tell me a joke?"}],
    # )

    # print(response.choices[0].message)

    unit_test_code = unit_test_from_function(
        function_to_test=codes,
        print_text=True,
        engine=engine
    )

    with open(f"test_{functions_file}","w") as test_f:
        test_f.write(unit_test_code)
