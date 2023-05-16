# imports needed to run the code in this notebook
import os
import sys
import json
import ast
import openai  # used for calling the OpenAI API
from get_functions import import_all_modules
import re
import subprocess
import inspect
from typing import Any, Tuple, List  # type: ignore


class CodeToolbox:
    def __init__(self, **kwargs):
        """
        Initialize the CodeToolbox instance.

        Available configuration parameters:

        - platform (str, optional): code language/version or platforms that need to generate unit test. Defaults to "Python 3.9".
        - unit_test_package (str): package/ library used for unit testing, i.e. `pytest`, `unittest`, etc. Defaults to "pytest"
        - document (bool): Whether to generate documentation. Default is True.
        - unit_test (bool): Whether to run unit tests. Default is True.
        - conversion (bool): Whether to perform language conversion. Default is True.
        - conversion_target (str): The target language for conversion. Default is 'scala'.
        - max_tokens (int): The maximum number of tokens for ChatGPT. Default is 1000.
        - temperature (float): The temperature for ChatGPT. Default is 0.2.
        - reruns_if_fail (int): Number of reruns if a process fails. Default is 0.
        - model (str): The GPT model to use. Default is 'gpt-4'.
        - engine (str): The ChatGPT engine to use. Default is 'GPT4'.
        """
        self.config = {
            "document": True,
            "unit_test": True,
            "conversion": True,
            "conversion_target": "scala",
            "max_tokens": 1000,
            "temperature": 0.2,
            "reruns_if_fail": 0,
            "model": "gpt-4",
            "engine": "GPT4",
            "unit_test_package": "pytest",
            "doc_package": "sphinx",
            "platform": "python3.9",
        }
        self.config.update(kwargs)
        self.changed_code_files = sys.argv[1:]

    def chat_gpt_wrapper(self, input_messages=[]) -> Tuple[Any, List]:
        """Outputs a unit test for a given Python function, using a 3-step GPT-3 prompt."""

        # the init function for this classs is\
        # {init_str}\

        plan_response = openai.ChatCompletion.create(
            engine=engine,
            model=model,
            messages=input_messages,
            max_tokens=self.config["max_tokens"],
            temperature=self.config["temperature"],
            stream=False,
        )
        unit_test_completion = plan_response.choices[0].message.content
        input_messages.append({"role": "assistant", "content": unit_test_completion})
        # check the output for errors
        code_output = self.extract_all_python_code(unit_test_completion)
        try:
            ast.parse(code_output)
        except SyntaxError as e:
            print(f"Syntax error in generated code: {e}")
            if self.config["reruns_if_fail"] > 0:
                print("Rerunning...")
                self.config["reruns_if_fail"] -= 1  # decrement rerun counter when calling again
                return self.chat_gpt_wrapper(input_messages=input_messages)
        return code_output, input_messages

    @staticmethod
    def extract_all_python_code(string):
        start_marker = "```python"
        end_marker = "```"
        pattern = re.compile(f"{start_marker}(.*?)({end_marker})", re.DOTALL)
        matches = pattern.findall(string)
        if not matches:
            return None
        return "".join([match[0].strip() for match in matches])

    @staticmethod
    def convert_keys_to_str(dictionary):
        """
        Recursively convert dictionary keys to strings.
        """
        new_dict = {}
        for key, value in dictionary.items():
            new_key = str(key)  # Convert key to string
            if isinstance(value, dict):
                new_dict[new_key] = convert_keys_to_str(value)  # Recursively convert nested dictionaries
            elif callable(value):
                # new_dict[new_key] = value.__qualname__  # Convert function object to qualified name
                new_dict[new_key] = inspect.getsource(value)  # Convert function object to qualified name
            else:
                new_dict[new_key] = value
        return new_dict

    @staticmethod
    def has_function_changed(current_file, previous_file, file_key, function_name, class_name=None):
        """
        Check if a function has changed between current and previous versions of the file.
        """
        current_data = json.load(current_file)
        previous_data = json.load(previous_file)
        if class_name:
            current_function = current_data[file_key]["objects"][class_name][function_name]
            previous_function = previous_data[file_key]["objects"][class_name][function_name]
        else:
            current_function = current_data[file_key]["objects"][function_name]
            previous_function = previous_data[file_key]["objects"][function_name]
        return current_function != previous_function

    def method_function_processor(self, class_name=None, function_name="", func_str=""):
        class_part = "in class " + class_name if class_name else None
        self.doc_messages.append(
            {
                "role": "user",
                "content": f"provide documentation for {func_str} {class_part} that can be used in {self.config['doc_package']}",
            }
        )
        doc_code, self.doc_messages = self.chat_gpt_wrapper(input_messages=self.doc_messages)
        if len(self.doc_messages) > 4:
            self.doc_messages = self.doc_messages[:1] + self.doc_messages[-4:]
        # Open the file in read mode and read its content
        with open(self.file_path, "r") as file:
            file_content = file.read()
        if doc_code.startswith("class"):
            doc_code = "\n".join(doc_code.split("\n")[1:])
        else:
            doc_code = "    " + doc_code.replace("\n", "\n    ")
        # Replace a specific string in the file content
        new_content = file_content.replace(func_str, doc_code)

        # Open the file in write mode and write the new content to it
        with open(self.file_path, "w") as file:
            file.write(new_content)

        request_for_unit_test = f" provide unit test for the function `{function_name} {class_part}`.\
            ```python\
            {func_str} \
            ```\
            and the path of the function is {self.file_path}\
            "
        self.unit_test_messages.append({"role": "user", "content": request_for_unit_test})
        unit_test_code, self.unit_test_messages = self.chat_gpt_wrapper(input_messages=self.unit_test_messages)
        if len(self.unit_test_messages) > 4:
            doc_code = doc_code[:1] + doc_code[-4:]
        # generated_unit_test = f"{function_name} in class {class_name}`\n{unit_test_code}"
        current_test_path = f"test_code/unit_test/test_{class_name}_{function_name}.py"
        with open(current_test_path, "w") as test_f:
            test_f.write(unit_test_code)

    def object_processor(self, obj_key, obj_value):
        if type(obj_value) == dict:
            for class_method_name, class_method in obj_value.items():
                class_name = str(class_method).split(".")[0].split(" ")[1]
                function_name = str(class_method).split(".")[1].split(" ")[0]
                function_to_test = inspect.getsource(class_method)
                self.method_function_processor(
                    class_name=class_name, function_name=function_name, func_str=function_to_test
                )
        else:
            function_name = obj_key
            function_to_test = inspect.getsource(obj_value)
            self.method_function_processor(class_name=None, function_name=function_name, func_str=function_to_test)

    def main_pipeline(
        self,
        directory: str,  # path to the entire repo folder
        repo_explanation: str,  # explanation of the project repo - got from documentation
        unit_test_package: str = "pytest",
        doc_package: str = "sphinx",
        platform: str = "Python 3.9",
    ):
        """pipeline to generate unit test for all code files that contain modules in a directory

        Args:
            directory (str): path to the entire repo folder
            repo_explanation (str): high level explanation of what the project does and what needs to have unit test generated
                1. Indicate which code files/ classes/ functions need to generate unit test
                2. List all dependencies (custom attribute values that OpenAI cannot generate randomly) needed to the run the codes (
                    if there's any config file, testing path (S3), schema of the dataframe, clearly state in this explanation as well)
                For example, in the DQ check project, repo explanation is as below:
                    - This project is run mainly by file `dq_utility.py` file. This file is packaged to be used as library
                    - This `dq_utility.py` includes `DataCheck` class along with its methods to check the data quality of a dataframe.
                    It will generate a csv output of the lines with errors in a csv file
                    - Some needed info for dependencies are as below (class attributes):
                        * rules files (csv) that can provide the schema (columns) of DF - config_path (S3 path where hold the config csv file in this case)
                        * name of the file to have data quality check (proper file name included in the config csv rules file) - file_name attribute
                        * the source (vendor) of the file to have data quality check - src_system attribute
        """
        # TODO: in current way, you cannot do java or something else with python. change platform and unit_test_package maybe.

        object_dict = {}
        directory_dict = {}
        object_dict, directory_dict = import_all_modules(
            directory=directory, object_dict=object_dict, directory_dict=directory_dict
        )

        # i = 0

        doc_prompt = f"""you are providing documentation and typing (type hints) of code to be used in {doc_package}, as an example for the function
        ```python
        def read_s3_file(self, file_path):
            file_res = urlparse(file_path)
            try:
                file_obj = s3_resource.Object(file_res.netloc, file_res.path.lstrip("/"))
                return file_obj.get()["Body"].read()
            except ClientError:
                raise FileNotFoundError(f"File cannot be found in S3 given path file_path"):
        ```
        this is a proper response:
        ```python
        def read_s3_file(self, file_path:str)->str:
        \"\"\"
        Reads the contents of a file from an S3 bucket.
        :param file_path: The S3 URI of the file to read, e.g. "s3://my-bucket/my-file.txt".
        :type file_path: str
        :return: The contents of the file as a byte string.
        :rtype: bytes
        :raises FileNotFoundError: If the file cannot be found in the specified S3 bucket.
        :Example:
        (some examples)
        \"\"\"
        file_res = urlparse(file_path)
        try:
            file_obj = s3_resource.Object(file_res.netloc, file_res.path.lstrip("/"))
            return file_obj.get()["Body"].read()
        except ClientError:
            raise FileNotFoundError(f"File cannot be found in S3 given path file_path")
        ```
        """
        self.doc_messages = []
        self.doc_messages.append({"role": "system", "content": doc_prompt})
        unit_test_prompt = f"you are providing unit test using {unit_test_package}` and {platform}\
            {repo_explanation}. to give details about the structure of the repo look at the dictionary below, it includes all files\
            and if python, all function and classes, if json first and second level keys and if csv, the column names :{directory_dict},"
        self.unit_test_messages = []
        self.unit_test_messages.append({"role": "system", "content": unit_test_prompt})
        # TODO: conversion
        # conversion_messages=[]
        # conversion_prompt= f"your task is to convert the code into {target_conversion}"
        if not os.path.exists(
            "current_modules.json"
        ):  # this is the first push, so all unit tests need to be generated (no modification/ deletion)
            for self.file_path, objects in object_dict.items():
                # generated_unit_test = ""
                if "objects" in objects:
                    for obj_key, obj_value in objects["objects"].items():
                        if obj_value:
                            self.object_processor(obj_key, obj_value)
                    # TODO: merge all unit test into one file
                    # unit_test_path = file_path[::-1].replace('\\','/test_',1)[::-1]
                    # with open(unit_test_path, "w") as test_f:
                    #     test_f.write(generated_unit_test)
        else:  # detect the change files/ functions and regenerate/ delete unit tests based on that
            if len(self.changed_code_files) > 0:
                print("there're changed files")
                for file in self.changed_code_files:
                    print(file)  # test_code/dq_utility.py
                    file_key = file.replace("/", "\\")  # test_code\\dq_utility.py
                    if os.path.exists("previous_modules.json"):
                        # compare with the "current_modules.json" and detect the different modules, then regenerare or delete unit tests where needed
                        with open("current_modules.json", "r") as current_file, open(
                            "previous_modules.json", "r"
                        ) as previous_file:
                            current_data = json.load(current_file)
                            previous_data = json.load(previous_file)
                            if file_key not in current_data:
                                if file_key in previous_data:  # meaning file is deleted after push
                                    # delete unit test for all functions in this file
                                    if "objects" in previous_data[file_key]:
                                        for obj_key, obj_value in previous_data[file_key]["objects"].items():
                                            if obj_value:
                                                class_name = None
                                                function_name = ""
                                                if type(obj_value) == dict:
                                                    for class_method_name, class_method in obj_value.items():
                                                        class_name = str(class_method).split(".")[0].split(" ")[1]
                                                        function_name = str(class_method).split(".")[1].split(" ")[0]
                                                        unit_test_file = (
                                                            f"test_code/unit_test/test_{class_name}_{function_name}.py"
                                                        )
                                                        if os.path.exists(unit_test_file):
                                                            try:
                                                                # Delete the file
                                                                os.remove(unit_test_file)
                                                                print("File deleted successfully!")
                                                            except OSError as e:
                                                                # Handle the case where the file does not exist or cannot be deleted
                                                                print(f"Error deleting the file: {e}")
                                                else:
                                                    function_name = obj_key
                                                    unit_test_file = (
                                                        f"test_code/unit_test/test_{class_name}_{function_name}.py"
                                                    )
                                                    if os.path.exists(unit_test_file):
                                                        try:
                                                            # Delete the file
                                                            os.remove(unit_test_file)
                                                            print("File deleted successfully!")
                                                        except OSError as e:
                                                            # Handle the case where the file does not exist or cannot be deleted
                                                            print(f"Error deleting the file: {e}")
                            elif file_key not in previous_data:
                                if file_key in current_data:  # meaning file is just added after push
                                    # generate unit tests for all functions in this file
                                    if "objects" in current_data[file_key]:
                                        for obj_key, obj_value in current_data[file_key]["objects"].items():
                                            if obj_value:
                                                self.object_processor(obj_key, obj_value)
                            elif (
                                file_key in current_data and file_key in previous_data
                            ):  # meaning file has some modifications in content
                                # detect the class/ function that got modified and regenerate unit test
                                if "objects" in previous_data[file_key]:
                                    for obj_key, obj_value in previous_data[file_key]["objects"].items():
                                        if obj_value:
                                            class_name = None
                                            function_name = ""
                                            if type(obj_value) == dict:
                                                for class_method_name, class_method in obj_value.items():
                                                    class_name = str(class_method).split(".")[0].split(" ")[1]
                                                    function_name = str(class_method).split(".")[1].split(" ")[0]
                                                    with open("current_modules.json", "r") as current_file, open(
                                                        "previous_modules.json", "r"
                                                    ) as previous_file:
                                                        function_changed = self.has_function_changed(
                                                            current_file,
                                                            previous_file,
                                                            file_key,
                                                            class_name,
                                                            function_name,
                                                        )
                                                        if function_changed:
                                                            self.method_function_processor(
                                                                class_name=class_name,
                                                                function_name=function_name,
                                                                func_str=current_data[file_key]["objects"][class_name][
                                                                    function_name
                                                                ],
                                                            )

                                            else:
                                                function_name = obj_key
                                                with open("current_modules.json", "r") as current_file, open(
                                                    "previous_modules.json", "r"
                                                ) as previous_file:
                                                    function_changed = self.has_function_changed(
                                                        current_file, previous_file, file_key, class_name, function_name
                                                    )
                                                    if function_changed:
                                                        self.method_function_processor(
                                                            class_name=None,
                                                            function_name=function_name,
                                                            func_str=current_data[file_key]["objects"][function_name],
                                                        )
            else:
                print("no files have been changed. No actions needed")
                # return

        # Save the current state to `current_modules.json`
        converted_object_dict = self.convert_keys_to_str(object_dict)
        with open("current_modules.json", "w") as file:
            json.dump(converted_object_dict, file, indent=4)


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
    code_toolbox = CodeToolbox()

    # code_toolbox.main_pipeline(
    #     directory="test_code",
    #     repo_explanation="This repo uses the dq_utility to check the data quality based on different sources given in\
    #         csv files like az_ca_pcoe_dq_rules_innomar, it will generate a csv output of the lines with errors in a csv file, to use the repo u can:\
    #         from dq_utility import DataCheck\
    #         from pyspark.sql import SparkSession\
    #         spark = SparkSession.builder.getOrCreate()\
    #         df=spark.read.parquet('test_data.parquet')\
    #         Datacheck(source_df=df,\
    #         spark_context= spark,\
    #         config_path=s3://config-path-for-chat-gpt-unit-test/config.json,\
    #         file_name=az_ca_pcoe_dq_rules_innomar.csv,\
    #         src_system=bioscript)",
    # )
    print(code_toolbox.changed_code_files)
