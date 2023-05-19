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
            'document': True,
            'unit_test': True,
            'conversion': False,
            'conversion_target': 'scala',
            'max_tokens': 1000,
            'temperature': 0,
            'reruns_if_fail': 0,
            'model': 'gpt-4',
            'engine': 'GPT4',
            'unit_test_package':'pytest',
            'doc_package':'sphinx',
            'platform':'python3.9'
        }
        self.language='python'
        self.config.update(kwargs)
    def chat_gpt_wrapper(self,input_messages=[],fail_rerun=2) -> Tuple[Any, List]:
        """Outputs a unit test for a given Python function, using a 3-step GPT-3 prompt."""

        # the init function for this classs is\
        # {init_str}\

        plan_response = openai.ChatCompletion.create(
            engine=self.config["engine"],
            model=self.config["model"],
            messages=input_messages,
            max_tokens=self.config["max_tokens"],
            temperature=self.config["temperature"],
            stream=False,
        )
        unit_test_completion = plan_response.choices[0].message.content
        input_messages.append({"role": "assistant", "content": unit_test_completion})
        # check the output for errors
        code_output = self.extract_all_code(unit_test_completion,self.language)
        try:
            if code_output:
                ast.parse(code_output)
            else:
                return self.chat_gpt_wrapper(input_messages=input_messages,fail_rerun=fail_rerun-1)


        except SyntaxError as e:
            print(f"Syntax error in generated code: {e}")
            if self.config["reruns_if_fail"] > 0:
                print("Rerunning...")
                return self.chat_gpt_wrapper(input_messages=input_messages,fail_rerun=fail_rerun-1)
        return code_output, input_messages

    @staticmethod
    def extract_all_code(string,language='python'):
        start_marker = f"```{language}"
        end_marker = "```"
        pattern = re.compile(f"{start_marker}(.*?)({end_marker})", re.DOTALL)
        matches = pattern.findall(string)
        if not matches:
            return None
        return "".join([match[0].strip() for match in matches])

    def convert_keys_to_str(self,dictionary):
        """
        Recursively convert dictionary keys to strings.
        """
        new_dict = {}
        for key, value in dictionary.items():
            new_key = str(key)  # Convert key to string
            if isinstance(value, dict):
                new_dict[new_key] = self.convert_keys_to_str(value)  # Recursively convert nested dictionaries
            else:
                new_dict[new_key] = value
        return new_dict

    @staticmethod
    def has_function_changed(current_data, previous_data, file_key, function_name, class_name=None):
        """
        Check if a function has changed between current and previous versions of the file.
        """
        if class_name:
            current_function = current_data[file_key]["objects"][class_name][function_name]
            previous_function = previous_data[file_key]["objects"][class_name][function_name]
        else:
            current_function = current_data[file_key]["objects"][function_name]
            previous_function = previous_data[file_key]["objects"][function_name]
        return current_function != previous_function
    @staticmethod
    def delete_unit_test_file_for_each_function(class_name=None, function_name=""):
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
    def object_deleter(self, obj_key, obj_value):
        if type(obj_value) == dict:
            for class_method_name, class_method in obj_value.items():
                class_name = str(class_method).split(".")[0].split(" ")[1]
                function_name = str(class_method).split(".")[1].split(" ")[0]
                self.delete_unit_test_file_for_each_function(class_name, function_name)
        else:
            class_name = None
            function_name = obj_key
            self.delete_unit_test_file_for_each_function(class_name, function_name)

    def documenter(self,func_str):
        doc_prompt = f"""you are providing documentation and typing (type hints) of \
            code to be used in {self.config['doc_package']},\
            provide the typing imports in different code snippet, as an example for this request
        ```python
        def sum(a,b):
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                raise TypeError("Both parameters must be numeric values.")
            return a+b
        ```
        this is a proper response:
        ```python
        from typing import Union
        def sum(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
            \"\"\"
            Returns the sum of two numbers.
            Args:
                a (int or float): The first number.
                b (int or float): The second number.
            Returns:
                int or float: The sum of `a` and `b`.
            Raises:
                TypeError: If `a` or `b` is not a numeric value.
            Examples:
                >>> sum(2, 3)
                5
                >>> sum(4.5, 2.5)
                7.0
            \"\"\"
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                raise TypeError("Both parameters must be numeric values.")
            return a + b
        ```
        """
        self.doc_messages=[]
        self.doc_messages.append({"role":"system","content": doc_prompt})
        self.doc_messages.append({"role":"user","content":f"provide {self.config['doc_package']} docstring documentation and typehints for {func_str} in {class_part}, do not provide any other imports that are not used in typing and do not provide multiple options, just one code, if it is a method in a class, do not provide any other code but the method itself and imports"})
        doc_code,self.doc_messages = self.chat_gpt_wrapper(input_messages=self.doc_messages)

        # Open the file in read mode and read its content
        with open(self.file_path, 'r') as file:
            file_content = file.read()
        import_pattern = r"(?m)^((?:from|import)\s+.+)$"
        import_matches = []
        if 'import' in self.doc_messages[-1]['content']:
            # Find all matches of the pattern in the code string
            import_matches = re.findall(import_pattern, doc_code)
            doc_code= re.sub(import_pattern, '', doc_code)
        doc_code = doc_code.lstrip('\n')
        if doc_code.startswith('class'):
            doc_code='\n'.join(doc_code.split('\n')[1:])+ '\n'
        else:
            doc_code='    '+doc_code.replace('\n','\n    ') + '\n'
        new_content = file_content.replace(func_str, doc_code)
        all_imports = re.findall(import_pattern, new_content)
        for import_str in import_matches:
            if import_str not in all_imports:
                new_content = import_str + '\n' + new_content
        new_content = re.sub(r"\n{2,}", "\n\n", new_content)
        with open(self.file_path, 'w') as file:
            file.write(new_content)

        command = ['autoflake', '--in-place', '--remove-all-unused-imports', self.file_path]
        subprocess.run(command, check=True)
        command = ['isort', self.file_path]
        subprocess.run(command, check=True)
        if len(self.doc_messages)>1:
            self.doc_messages = self.doc_messages[:1]
    def create_code_file(self,code, target):
        file_extension = {
            'python': 'py',
            'scala': 'scala',
            'c++': 'cpp'
            # Add more mappings as needed
        }
        folder_name = target.lower()
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        suggested_file_name = f"converted_code.{file_extension.get(target, 'txt')}"
        suggested_file_path = os.path.join(folder_name, suggested_file_name)

        file_mode = 'a' if os.path.exists(suggested_file_path) else 'w'
        with open(suggested_file_path, file_mode) as file:
            file.write(code)

        if file_mode == 'w':
            print(f"Code successfully saved to '{suggested_file_path}'")
        else:
            print(f"Code successfully appended to '{suggested_file_path}'")
    def converter(self,func_str):
        conv_prompt = f"you are providing conversion to {self.config['conversion_target']} of the codes you are given {self.repo_explanation}"
        self.conv_messages = []
        self.conv_messages.append({"role": "system", "content": conv_prompt})
        self.conv_messages.append({"role":"user","content":f"convert the following code to {self.config['conversion_target']}\
                                     {self.class_part},{func_str} "})
        self.language = self.config['conversion_target']
        conv_code,self.conv_messages = self.chat_gpt_wrapper(input_messages=self.conv_messages)
        self.language = 'python'
        # Open the file in read mode and read its content
        self.create_code_file(conv_code,self.config['conversion_target'])
    def unit_tester(self,class_name='',func_str='',function_name=''):
        unit_test_prompt = f"you are providing unit test using {self.config['unit_test_package']}` and\
            {self.config['platform']} {self.repo_explanation}. to give details about the structure of\
            the repo look at the dictionary below, it includes all files and if python, all function\
            and classes, if json first and second level keys and if csv, the column names :{self.directory_dict},"
        self.unit_test_messages = []
        self.unit_test_messages.append({"role": "system", "content": unit_test_prompt})
        request_for_unit_test = f" provide unit test for the function `{self.class_part}`.\
            ```python\
            {func_str} \
            ```\
            and the path of the function is {self.file_path}\
            "
        self.unit_test_messages.append({"role": "user", "content": request_for_unit_test})
        unit_test_code, self.unit_test_messages = self.chat_gpt_wrapper(input_messages=self.unit_test_messages)
        # if len(self.unit_test_messages) > 4:
        #     doc_code = doc_code[:1] + doc_code[-4:]
        # generated_unit_test = f"{function_name} in class {class_name}`\n{unit_test_code}"
        current_test_path = f"test_code/unit_test/test_{class_name}_{function_name}.py"
        with open(current_test_path, "w") as test_f:
            test_f.write(unit_test_code)

    def method_function_processor(self,class_name=None,function_name='',func_str=''):
        # import_matches = []
        self.class_part = 'in class '+ class_name if class_name else None
        if self.config['document']:
            self.documenter(func_str=func_str)
        self.unit_tester(func_str=func_str,function_name=function_name)
        if self.config['conversion']:
            self.converter(func_str=func_str)

    def object_processor(self, obj_key, obj_value):
        if type(obj_value) == dict:
            for method_name, class_method in obj_value.items():
                class_name = str(class_method).split(".")[0].split(" ")[1]
                self.method_function_processor(class_name=class_name,function_name=method_name,func_str=class_method)
        else:
            function_name = obj_key
            self.method_function_processor(class_name=None,function_name=function_name,func_str=obj_value)

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
        self.repo_explanation=repo_explanation
        # TODO: in current way, you cannot do java or something else with python. change platform and unit_test_package maybe.

        object_dict = {}
        self.directory_dict = {}
        object_dict, self.directory_dict = import_all_modules(
            directory=directory, object_dict=object_dict, directory_dict=self.directory_dict
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
            and if python, all function and classes, if json first and second level keys and if csv, the column names :{self.directory_dict},"
        self.unit_test_messages = []
        self.unit_test_messages.append({"role": "system", "content": unit_test_prompt})
        # TODO: conversion
        # conversion_messages=[]
        # conversion_prompt= f"your task is to convert the code into {target_conversion}"
        if os.path.exists("current_modules.json"):
            with open("current_modules.json", "r") as current_file:
                self.current_data = json.load(current_file)

        if os.path.exists("previous_modules.json"):
            with open("previous_modules.json", "r") as previous_file:
                self.previous_data = json.load(previous_file)
        else:
            self.previous_data=None

        # loop through all files in the current repo
        for self.file_path, objects in object_dict.items():
            # generated_unit_test = ""
            if "objects" in objects:
                if not os.path.exists(
                    "current_modules.json"
                ):  # this is the first push, so all unit tests, documents need to be generated (no modification/ deletion)
                    self.config['document'] = True
                    for obj_key, obj_value in objects["objects"].items():
                        if obj_value:
                            self.object_processor(obj_key, obj_value)
                    self.config['document'] = False
                elif os.path.exists("previous_modules.json"):  # check if file already exists before push
                    if self.file_path not in self.previous_data:  # file does not exist previous, meaning this file is newly created so whole new unit tests need to be generated
                        for obj_key, obj_value in objects["objects"].items():
                            if obj_value:
                                self.object_processor(obj_key, obj_value)
                    else:
                        # if file exists previously
                        # detect the class/ function that got modified and regenerate unit test
                        for obj_key, obj_value in objects["objects"].items(): #loop through all objects in file to detect the changes
                            if obj_value:
                                class_name = None
                                function_name = ""
                                if type(obj_value) == dict: #file has class and functions
                                    for class_method_name, class_method in obj_value.items():
                                        class_name = str(class_method).split(".")[0].split(" ")[1]
                                        function_name = str(class_method).split(".")[1].split(" ")[0]
                                        function_changed = self.has_function_changed(
                                            self.current_data,
                                            self.previous_data,
                                            self.file_path,
                                            class_name,
                                            function_name,
                                        )
                                        if function_changed:
                                            self.method_function_processor(
                                                class_name=class_name,
                                                function_name=function_name,
                                                func_str=self.current_data[self.file_path]["objects"][class_name][
                                                    function_name
                                                ],
                                            )
                                else: #file only has functions
                                    function_name = obj_key
                                    function_changed = self.has_function_changed(
                                        self.current_data, self.previous_data, self.file_path, class_name, function_name
                                    )
                                    if function_changed:
                                        self.method_function_processor(
                                            class_name=None,
                                            function_name=function_name,
                                            func_str=self.current_data[self.file_path]["objects"][function_name],
                                        )
                else: #when `current_modules.json` exist but `previous_modules.json` doesn't exist
                    # `current_modules.json` exist when `main.py` is already executed -> not the first push -> need to do comparision
                    # `previous_modules.json` doesn't exist when `main.py` is executed without pushing (because every push will make `previous_modules.json`)
                    print('no action needed')

                # TODO: merge all unit test into one file
                # unit_test_path = file_path[::-1].replace('\\','/test_',1)[::-1]
                # with open(unit_test_path, "w") as test_f:
                #     test_f.write(generated_unit_test)

        # loop through all files in the previous repo
        if self.previous_data:
            for self.previous_file_path, objects in self.previous_data.items():
                if self.previous_file_path in self.current_data:
                    if "objects" in objects:
                        #loop through objects to delete certain object
                        if "objects" in self.current_data[self.previous_file_path]:
                            for obj_key, obj_value in objects["objects"].items():
                                if obj_value:
                                    if obj_key in self.current_data[self.previous_file_path]["objects"]:
                                        if type(obj_value) == dict:
                                            if type(self.current_data[self.previous_file_path]["objects"][obj_key]) == dict:
                                                for class_method_name, class_method in obj_value.items():
                                                    class_name = str(class_method).split(".")[0].split(" ")[1]
                                                    function_name = str(class_method).split(".")[1].split(" ")[0]
                                                    if class_method_name not in self.current_data[self.previous_file_path]["objects"][obj_key][obj_value]:
                                                        self.delete_unit_test_file_for_each_function(class_name, function_name)
                                                    else:
                                                        if class_method not in self.current_data[self.previous_file_path]["objects"][obj_key][obj_value][class_method_name]:
                                                            self.delete_unit_test_file_for_each_function(class_name, function_name)
                                            else:
                                                for class_method_name, class_method in obj_value.items():
                                                    class_name = str(class_method).split(".")[0].split(" ")[1]
                                                    function_name = str(class_method).split(".")[1].split(" ")[0]
                                                    self.delete_unit_test_file_for_each_function(class_name, function_name)
                                        else:
                                            if obj_value in self.current_data[self.previous_file_path]["objects"][obj_key]:
                                                class_name = None
                                                function_name = obj_key
                                                self.delete_unit_test_file_for_each_function(class_name, function_name)
                                    else:
                                        self.object_deleter(obj_key, obj_value)
                        else:
                            for obj_key, obj_value in objects["objects"].items():
                                if obj_value:
                                    self.object_deleter(obj_key, obj_value)
                else:
                    if "objects" in objects:
                        for obj_key, obj_value in objects["objects"].items():
                            if obj_value:
                                self.object_deleter(obj_key, obj_value)

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

    code_toolbox.main_pipeline(
        directory="test_code/data_quality_package",
        repo_explanation="This repo uses the dq_utility to check the data quality based on different sources given in\
            csv files like az_ca_pcoe_dq_rules_innomar, it will generate a csv output of the lines with errors in a csv file, to use the repo u can:\
            from dq_utility import DataCheck\
            from pyspark.sql import SparkSession\
            spark = SparkSession.builder.getOrCreate()\
            df=spark.read.parquet('test_data.parquet')\
            Datacheck(source_df=df,\
            spark_context= spark,\
            config_path=s3://config-path-for-chat-gpt-unit-test/config.json,\
            file_name=az_ca_pcoe_dq_rules_innomar.csv,\
            src_system=bioscript)",
    )
    # print(code_toolbox.main_pipeline())
