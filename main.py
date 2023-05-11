# imports needed to run the code in this notebook
import ast
import code  # used for detecting whether generated Python code is valid
import openai  # used for calling the OpenAI API
from get_functions import import_all_modules
import re
import subprocess
import inspect

# example of a function that uses a multi-step prompt to write unit tests


def unit_test_from_function(
    unit_test_package: str = "pytest",
    input_messages=[],
    engine: str = "GPT4",
    model="gpt-4",
    max_tokens: int = 1000,
    temperature: float = 0.4,
    reruns_if_fail: int = 0,
) -> str:
    """Outputs a unit test for a given Python function, using a 3-step GPT-3 prompt."""

    # the init function for this classs is\
    # {init_str}\

    plan_response = openai.ChatCompletion.create(
        engine=engine,
        model=model,
        messages=input_messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=False,
    )
    unit_test_completion = plan_response.choices[0].message.content
    input_messages.append({"role": "assistant", "content": plan_response.choices[0].message.content})
    # check the output for errors
    code_output = extract_all_python_code(unit_test_completion)
    try:
        ast.parse(code_output)
    except SyntaxError as e:
        print(f"Syntax error in generated code: {e}")
        if reruns_if_fail > 0:
            print("Rerunning...")
            return unit_test_from_function(
                unit_test_package=unit_test_package,
                messages=input_messages,
                engine=engine,
                max_tokens=max_tokens,
                temperature=temperature,
                reruns_if_fail=reruns_if_fail - 1,  # decrement rerun counter when calling again
            )
    return code_output, input_messages


def extract_all_python_code(string):
    start_marker = "```python"
    end_marker = "```"
    pattern = re.compile(f"{start_marker}(.*?)({end_marker})", re.DOTALL)
    matches = pattern.findall(string)
    if not matches:
        return None
    return "".join([match[0].strip() for match in matches])


def get_changed_py_files_after_commit():
    # Get the list of changed files
    output = subprocess.check_output(['git', 'diff', '--name-status', 'HEAD^', 'HEAD'])

    # for file in output.splitlines():
    #     status, filename = file.split('\t')
    #     print(f"Status: {status}, Filename: {filename}")
    # Filter for only Python files
    python_files = [f for f in output.decode().split('\n') if f.endswith('.py')]

    # Get the type of change for each Python file
    changes = {}
    for file in python_files:
        print(file)
        try:
            status, filename = file.split('\t')
            print(f"Status: {status}, Filename: {filename}")
            changes[filename] = status
        except ValueError:
            print(f"Skipping invalid line: {file}")

    return changes



if __name__ == "__main__":
    # import os
    # from dotenv import load_dotenv

    # load_dotenv()
    # import os
    # import openai

    # openai.api_type = "azure"
    # openai.api_base = "https://aoaihackathon.openai.azure.com/"
    # openai.api_version = "2023-03-15-preview"
    # openai.api_key = os.getenv("OPENAI_API_KEY")
    # engine = "GPT4"
    # model = "gpt-4"
    # object_dict = {}
    # directory_dict = {}
    # object_dict, directory_dict = import_all_modules(
    #     "test_code", object_dict=object_dict, directory_dict=directory_dict
    # )
    # i = 0
    # messages = []
    # unit_test_package = "pytest"
    # platform = "python 3.9"
    # user_input = "This repo uses the dq_utility to check the data quality based on different sources given in\
    #     csv files like az_ca_pcoe_dq_rules_innomar, it will generate a csv output of the lines with errors in a csv file, to use the repo u can:\
    #     from dq_utility import DataCheck\
    #     from pyspark.sql import SparkSession\
    #     spark = SparkSession.builder.getOrCreate()\
    #     df=spark.read.parquet('test_data.parquet')\
    #     Datacheck(source_df=df,\
    #     spark_context= spark,\
    #     config_path=s3://config-path-for-chat-gpt-unit-test/config.json,\
    #     file_name=az_ca_pcoe_dq_rules_innomar.csv,\
    #     src_system=bioscript)"
    # repo_explanation = f"you are providing unit test using {unit_test_package}` and Python 3.9\
    #     {user_input}. to give details about the structure of the repo look at the dictionary below, it includes all files\
    #     and if python, all function and calsses, if json first and second level keys and if csv, the column names :{directory_dict}"
    # messages.append({"role": "system", "content": repo_explanation})
    # for file_path, objects in object_dict.items():
    #     if "objects" in objects:
    #         for obj_key, obj_value in objects["objects"].items():
    #             if obj_value:
    #                 if type(obj_value) == dict:
    #                     for class_method_name, class_method in obj_value.items():
    #                         # if '__init__' in str(class_method).split(' at ')[0].replace('<','').replace('.','_').replace(' ','_'):
    #                         #     init_str = inspect.getsource(class_method)
    #                         #     continue
    #                         # if __init__function:
    #                         #     init_str=f'the __init__ function for this class is: {__init__function}'\
    #                         class_name = str(class_method).split(".")[0].split(" ")[1]
    #                         function_name = str(class_method).split(".")[1].split(" ")[0]
    #                         function_to_test = inspect.getsource(class_method)
    #                         prompt_to_explain_the_function = f" provide unit test for the function `{function_name} in {class_name}`.\
    #                             ```python\
    #                             {function_to_test} \
    #                             ```\
    #                             and the path of the function is {file_path}\
    #                             "
    #                         messages.append({"role": "user", "content": prompt_to_explain_the_function})
    #                         unit_test_code, messages = unit_test_from_function(
    #                             input_messages=messages,
    #                             engine=engine,
    #                             model=model,
    #                         )
    #                         current_test_path = f"test_code/unit_test/test_{class_method_name}.py"
    #                         with open(current_test_path, "w") as test_f:
    #                             test_f.write(unit_test_code)
    #                 else:
    #                     # TODO: add the prompt explain....
    #                     unit_test_code, messages = unit_test_from_function(
    #                         input_messages=messages,
    #                         engine=engine,
    #                         model=model,
    #                     )
    #                     current_test_path = (
    #                         f"test_code/unit_test/test_{str(obj_value).split(' at ')[0].replace('<','')}.py"
    #                     )
    #                     with open(current_test_path, "w") as test_f:
    #                         test_f.write(unit_test_code)
    #                 MAX_RETRIES = 3
    #                 retry_count = 0
    #                 fixed = False
    #                 i += 1
    #                 if i > 3:
    #                     break

        # print('done')

    print(get_changed_py_files_after_commit())
