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
    function_to_test: str,  # Python function to test, as a string
    # unit testing package; use the name as it appears in the import statement
    unit_test_package: str = "pytest",
    # minimum number of test case categories to cover (approximate)
    approx_min_cases_to_cover: int = 1,
    # optionally prints text; helpful for understanding the function & debugging
    print_text: bool = False,
    directory_dict=None,
    function_name=None,
    __init__function=None,
    input_messages=[],
    engine: str = "GPT4",  # engine used to generate text plans in steps 1, 2, and 2b
    model="gpt-4",
    # can set this high, as generations should be stopped earlier by stop sequences
    max_tokens: int = 1000,
    # temperature = 0 can sometimes get stuck in repetitive loops, so we use 0.4
    temperature: float = 0.4,
    # if the output code cannot be parsed, this will re-run the function up to N times
    reruns_if_fail: int = 0,
) -> str:
    """Outputs a unit test for a given Python function, using a 3-step GPT-3 prompt."""
    if __init__function:
        init_str=f'the __init__ function for this class is: {__init__function}'
    # tree_output = 'if you need any config or import, the tree of the repo is this, find it and give the path.' + \
    #     subprocess.run(['tree', 'test_code/'],
    #                    capture_output=True, text=True).stdout
    # create a markdown-formatted prompt that asks GPT-3 to complete an explanation of the function, formatted as a bullet list
    prompt_to_explain_the_function = f" provide unit test for the function `{function_name}`.\
```python\
{function_to_test} \
```\
and the path of the function is {function_to_test[1]}\
"
# the init function for this classs is\
# {init_str}\

    plan_response = openai.ChatCompletion.create(
        engine=engine,
        model=model,
        messages=input_messages,
        # stop=["\n\n", "\n\t\n", "\n    \n"],
        max_tokens=max_tokens,
        temperature=temperature,
        stream=False,
    )

    # append this unit test prompt to the results from step 3he_unit_test

    # send the prompt to the API, using ``` as a stop sequence to stop at the end of the code block
    # unit_test_completion = ""
    unit_test_completion = plan_response.choices[0].message.content
    input_messages.append( {"role": "assistant", "content":plan_response.choices[0].message.content })
    # check the output for errors
    code_output = extract_all_python_code(unit_test_completion)
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
    return code_output,input_messages


def extract_all_python_code(string):
    start_marker = '```python'
    end_marker = '```'
    pattern = re.compile(f'{start_marker}(.*?)({end_marker})', re.DOTALL)
    matches = pattern.findall(string)
    if not matches:
        return None
    return ''.join([match[0].strip() for match in matches])


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    import os
    import openai
    openai.api_type = "azure"
    openai.api_base = "https://aoaihackathon.openai.azure.com/"
    openai.api_version = "2023-03-15-preview"
    openai.api_key = os.getenv("OPENAI_API_KEY")
    engine = "GPT4"
    model = "gpt-4"
    object_dict = {}
    directory_dict = {}
    object_dict,directory_dict = import_all_modules("test_code", object_dict=object_dict,directory_dict=directory_dict)
    i = 0
    messages = []
    unit_test_package = 'pytest'
    platform = "python 3.9"
    user_input = "This repo uses the dq_utility to check the data quality based on different sources given in\
        csv files like az_ca_pcoe_dq_rules_innomar, it will generate a csv output of the lines with errors in a csv file, use:\
        from dq_utility import DataCheck\
        Datacheck(source_df=df,\
        spark_context= SparkSession.builder.getOrCreate(),\
        config_path=config.json,\
        file_name=az_ca_pcoe_dq_rules_bioscript.csv,\
        src_system=bioscript)"
    repo_explanation = f"you are providing unit test using {unit_test_package}` and Python 3.9\
        {user_input}. to give details about the structure of the repo look at the dictionary below, it includes all files\
        and if python, all function and calsses, if json first and second level keys and if csv, the column names :{directory_dict}"
    messages.append({"role": "system",
            "content": repo_explanation})
    for file_path, objects in object_dict.items():
        if 'objects' in objects:
            for obj_key, obj_value in objects['objects'].items():
                if obj_value:
                    if type(obj_value)==dict:
                        for class_method_name,class_method in obj_value.items():
                            if '__init__' in str(class_method).split(' at ')[0].replace('<','').replace('.','_').replace(' ','_'):
                                init_str = inspect.getsource(class_method)
                                continue
                            unit_test_code,messages = unit_test_from_function(
                            function_to_test= inspect.getsource(class_method),
                            function_name = str(class_method).split(' at ')[0].replace('<','').replace('.','_').replace(' ','_'),
                            __init__function=init_str,
                            file_path=file_path
                            directory_dict=directory_dict,
                            input_messages=messages,
                            print_text=True,
                            engine=engine,
                            model=model,
                        )
                            current_test_path = f'test_code/unit_test/test_{class_method_name}.py'
                            with open(current_test_path, "w") as test_f:
                                test_f.write(unit_test_code)
                    else:
                        unit_test_code = unit_test_from_function(
                            function_to_test= inspect.getsource(obj_value),
                            function_name = str(obj_value).split(' at ')[0].replace('<',''),
                            directory_dict=directory_dict,
                            print_text=True,
                            engine=engine,
                            model=model,
                        )
                        current_test_path = f"test_code/unit_test/test_{str(obj_value).split(' at ')[0].replace('<','')}.py"
                        with open(current_test_path, "w") as test_f:
                            test_f.write(unit_test_code)
                    MAX_RETRIES = 3
                    retry_count = 0
                    fixed = False
                    i += 1
                    if i > 3:
                        break
            
        # print('done')
