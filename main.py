import ast
import json
# imports needed to run the code in this notebook
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple, Union  # type: ignore

import openai  # used for calling the OpenAI API
import yaml
from get_functions import import_all_modules
from utils import remove_comments_and_docstrings


class CodeToolbox:
    def __init__(self, config_path: str) -> None:
        """
        Initialize the CodeToolbox instance.

        Args:
            config_path (str): Path to the configuration file.

        Attributes:
            config (Dict[str, Any]): Configuration parameters.
            language (str): The programming language used.

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
        with open(config_path, 'r') as file:
            self.config = yaml.safe_load(file)
        self.language = 'python'

    # ...

    # Other methods and attributes here

    def chat_gpt_wrapper(self, input_messages: List = [], fail_rerun: int = 2) -> Tuple[Any, List]:
        """
        Outputs a unit test for a given Python function, using a 3-step GPT-3 prompt.

        Args:
            input_messages (List, optional): A list of input messages for the GPT-3 prompt. Defaults to [].
            fail_rerun (int, optional): The number of times to rerun the GPT-3 prompt if it fails. Defaults to 2.

        Returns:
            Tuple[Any, List]: A tuple containing the generated unit test code and the updated input messages list.
        """

        # the init function for this class is
        # {init_str}

        plan_response = openai.ChatCompletion.create(
            engine=self.config["engine"],
            model=self.config["model"],
            messages=input_messages,
            max_tokens=self.config["max_tokens"],
            temperature=self.config["temperature"],
            stream=False,
        )
        unit_test_completion = plan_response.choices[0].message.content
        input_messages.append(
            {"role": "assistant", "content": unit_test_completion})
        # check the output for errors
        code_output = self.extract_all_code(
            unit_test_completion, self.language)
        try:
            if code_output:
                ast.parse(code_output)
            else:
                return self.chat_gpt_wrapper(input_messages=input_messages, fail_rerun=fail_rerun-1)

        except SyntaxError as e:
            print(f"Syntax error in generated code: {e}")
            if self.config["reruns_if_fail"] > 0:
                print("Rerunning...")
                return self.chat_gpt_wrapper(input_messages=input_messages, fail_rerun=fail_rerun-1)
        return code_output, input_messages
    def get_lowest_level_keys(self, dictionary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a dictionary containing the lowest level keys and their values from the input dictionary.

        Args:
            dictionary (Dict[str, Any]): The input dictionary to extract the lowest level keys from.

        Returns:
            Dict[str, Any]: A dictionary containing the lowest level keys and their values.

        Examples:
            >>> ct = CodeToolbox()
            >>> input_dict = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
            >>> ct.get_lowest_level_keys(input_dict)
            {'a': 1, 'c': 2, 'e': 3}
        """
        keys = {}
        for key, value in dictionary.items():
            if isinstance(value, dict):
                nested_keys = self.get_lowest_level_keys(value)
                keys.update(nested_keys)
            else:
                keys[key] = value
        return keys
    def extract_all_code(self, string, language='python'):
        """
        Extracts all code blocks of the specified language from a given string.

        Args:
            string (str): The input string containing code blocks.
            language (str, optional): The programming language of the code blocks. Defaults to 'python'.

        Returns:
            Optional[str]: A string containing all extracted code blocks separated by newlines, or None if no code blocks are found.
        """
        start_marker = f"```{language}"
        end_marker = "```"
        pattern = re.compile(f"{start_marker}(.*?)({end_marker})", re.DOTALL)
        matches = pattern.findall(string)
        if not matches:
            return None
        return "\n".join([match[0].strip() for match in matches])
        
    def convert_keys_to_str(self, dictionary: Dict[Any, Any]) -> Dict[str, Any]:
        """
        Recursively convert dictionary keys to strings.

        Args:
            dictionary (Dict[Any, Any]): The input dictionary with keys of any type.

        Returns:
            Dict[str, Any]: A new dictionary with keys converted to strings.

        Examples:
            >>> ct = CodeToolbox()
            >>> ct.convert_keys_to_str({1: "one", 2: {3: "three"}})
            {'1': 'one', '2': {'3': 'three'}}
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
    def has_function_changed(current_data: Dict[str, Any], previous_data: Dict[str, Any], file_key: str, function_name: str, class_name: str = None) -> bool:
        """
        Checks if a function has changed between two versions of data.

        Args:
            current_data (Dict[str, Any]): The current data dictionary.
            previous_data (Dict[str, Any]): The previous data dictionary.
            file_key (str): The key of the file in the data dictionaries.
            function_name (str): The name of the function to check.
            class_name (str, optional): The name of the class the function belongs to, if any. Defaults to None.

        Returns:
            bool: True if the function has changed, False otherwise.
        """
        if class_name:
            current_function = current_data[file_key]["objects"][class_name][function_name]
            previous_function = previous_data[file_key]["objects"][class_name][function_name]
        else:
            current_function = current_data[file_key]["objects"][function_name]
            previous_function = previous_data[file_key]["objects"][function_name]
        return current_function != previous_function
    @staticmethod
    def delete_unit_test_file_for_each_function(class_name: Optional[str] = None, function_name: str = "") -> None:
        """
        Deletes the unit test file for the specified function in the given class.

        Args:
            class_name (str, optional): The name of the class containing the function. Defaults to None.
            function_name (str): The name of the function for which the unit test file should be deleted.

        Returns:
            None

        Examples:
            >>> CodeToolbox.delete_unit_test_file_for_each_function("MyClass", "my_function")
            File deleted successfully!
        """
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
                self.delete_unit_test_file_for_each_function(
                    class_name, function_name)
        else:
            class_name = None
            function_name = obj_key
            self.delete_unit_test_file_for_each_function(
                class_name, function_name)

    def documenter(self, func_str: str,class_name:str=None) -> None:
        """
        Adds Sphinx docstring documentation and type hints to a given function or method in the CodeToolbox class.

        Args:
            func_str (str): The function or method signature to be documented.
            class_name (str): if it is a method in a class, give the class name.
        """
        doc_prompt = f"you are providing documentation and typing (type hints) of \
            code to be used in {self.config['doc_package']},\
            provide the typing imports in different code snippet, as an example for this request\
        {self.config['doc_example']}"
        self.doc_messages = []
        self.doc_messages.append({"role": "system", "content": doc_prompt})
        class_part = 'in' + self.class_name+'class' if class_name else ''
        self.doc_messages.append(
            {"role": "user", "content": f"provide {self.config['doc_package']} docstring documentation and typehints for {func_str} {class_part}, do not provide any other imports that are not used in typing and do not provide multiple options, just one code, if it is a method in a class, do not provide any other code but the method itself and imports"})
        doc_code, self.doc_messages = self.chat_gpt_wrapper(
            input_messages=self.doc_messages)

        # Open the file in read mode and read its content
        with open(self.file_path, 'r') as file:
            file_content = file.read()
        import_pattern = r"(?m)^((?:from|import)\s+.+)$"
        import_matches = []
        if 'import' in self.doc_messages[-1]['content']:
            # Find all matches of the pattern in the code string
            import_matches = re.findall(import_pattern, doc_code)
            doc_code = re.sub(import_pattern, '', doc_code)
        doc_code = doc_code.lstrip('\n')
        if doc_code.startswith('class'):
            doc_code = '\n'.join(doc_code.split('\n')[1:]) + '\n'
        else:
            doc_code = '    '+doc_code.replace('\n', '\n    ') + '\n'
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
        if len(self.doc_messages) > 1:
            self.doc_messages = self.doc_messages[:1]

    def create_code_file(self, code: str, target: str) -> None:
        """
        Creates a code file with the given code and target language.

        Args:
            code (str): The code to be written to the file.
            target (str): The target language for the code file.

        Returns:
            None
        """
        file_extension = self.config['conversion_target']
        folder_name = target.lower()
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        suggested_file_name = f"converted_code.{file_extension.get(target, 'txt')}"
        suggested_file_path = os.path.join(folder_name, suggested_file_name)

        file_mode = 'a' if os.path.exists(suggested_file_path) else 'w'
        with open(suggested_file_path, file_mode) as file:
            file.write(code)

    # Other methods and attributes here

    def converter(self, func_str: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Converts the given code to the target language specified in the config.

        Args:
            func_str (str): The code to be converted.

        Returns:
            Tuple[str, List[Dict[str, Any]]]: A tuple containing the converted code and the conversion messages.

        Examples:
            >>> code_toolbox = CodeToolbox(config, repo_explanation)
            >>> code_toolbox.converter("def sum(a, b): return a + b")
            ('function sum(a, b) { return a + b; }', [{'role': 'system', 'content': 'you are providing conversion to ...'}, {'role': 'user', 'content': 'convert the following code to ...'}])
        """
        conv_prompt = f"you are providing conversion to {self.config['conversion_target']} of the codes you are given {self.repo_explanation}"
        self.conv_messages = []
        self.conv_messages.append({"role": "system", "content": conv_prompt})
        self.conv_messages.append({"role": "user", "content": f"convert the following code to {self.config['conversion_target']}\
                                     {self.class_part},{func_str} "})
        self.language = self.config['conversion_target']
        conv_code, self.conv_messages = self.chat_gpt_wrapper(
            input_messages=self.conv_messages)
        self.language = 'python'
        self.create_code_file(conv_code, self.config['conversion_target'])

        return conv_code, self.conv_messages
    def find_key_value_pairs(self, dictionary: Dict[str, Any], target_key: str) -> List[Dict[str, Union[int, float]]]:
        """
        Finds all key-value pairs in a nested dictionary with the specified target_key.

        Args:
            dictionary (Dict[str, Any]): The dictionary to search for key-value pairs.
            target_key (str): The key to search for in the dictionary.

        Returns:
            List[Dict[str, Union[int, float]]]: A list of dictionaries containing the found key-value pairs.

        Examples:
            >>> ct = CodeToolbox()
            >>> nested_dict = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
            >>> ct.find_key_value_pairs(nested_dict, "e")
            [{'e': 3}]
        """
        key_value_pairs = []
        for key, value in dictionary.items():
            if key == target_key:
                key_value_pairs.append({key: value})
            if isinstance(value, dict):
                nested_key_value_pairs = self.find_key_value_pairs(value, target_key)
                key_value_pairs.extend(nested_key_value_pairs)
        return key_value_pairs
    @staticmethod
    def remove_unnecessary_text(input_string):
        # Remove ANSI escape sequences for colors and formatting
        color_regex = re.compile(r'\x1b\[[0-9;]*m')
        cleaned_string = color_regex.sub('', input_string)

        # Remove other non-printable characters and control characters
        cleaned_string = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', cleaned_string)

        # Remove leading and trailing whitespaces
        cleaned_string = cleaned_string.strip()

        return cleaned_string
    def unit_tester(self, class_obj='', func_str='', function_name=''):
        all_functions=self.get_lowest_level_keys(self.object_dict)
        other_func_str='the other functions that are used in this function are (do not provide unit test for them):'
        all_functions.pop(function_name)
        for fun_name in all_functions.keys():
            if fun_name in func_str:
                other_func_str +=f"{remove_comments_and_docstrings(all_functions[fun_name])}\n"
        if class_obj and not function_name=='__init__':
            init_method_str_for_class = self.find_key_value_pairs(self.object_dict,class_obj)[0][class_obj]['__init__']
            other_func_str += f"{remove_comments_and_docstrings(init_method_str_for_class)}\n"
        unit_test_prompt = f"you are providing unit test using {self.config['unit_test_package']}` and\
            {self.config['platform']}, you only provide code and do not explain anything."
        self.unit_test_messages = []
        self.unit_test_messages.append(
            {"role": "system", "content": unit_test_prompt})
        request_for_unit_test = f" provide unit test for the function `{self.class_part}```python\
            {remove_comments_and_docstrings(func_str)} \
            ```\,{other_func_str}`.\
            and the path of the function is {self.file_path} to give details about the structure of\
            the repo look at the dictionary below, it includes all files and if python, all function\
            and classes, if json first and second level keys and if csv, the column names :{self.directory_dict}\n\
            the tests are going to be in {self.config['test_path']}, provide full code unit test, so I can put your answer in a file and run pytest, do not ask me to change anything given the following: {self.repo_explanation}"
        self.unit_test_messages.append({"role": "user", "content": request_for_unit_test})
        unit_test_code, self.unit_test_messages = self.chat_gpt_wrapper(input_messages=self.unit_test_messages)
        class_name = str(class_obj).split('.')[1].split("'")[0]
        current_test_path = f"{self.config['directory']}/unit_test/test_{class_name}_{function_name}.py"
        with open(current_test_path, "w") as test_f:
            test_f.write(unit_test_code)
        command = [i for i in self.config['test_command'].split(' ')]
        command.append(f'unit_test/test_{class_name}_{function_name}.py')
        test_output = subprocess.run(command,capture_output=True, text=True)
        minimum_test_failure = self.config['test_failure_retry']
        #TODO: find if we can check the failures '= FAILURES =' in test_output.stdout or 
        while minimum_test_failure>0:
            if '= ERRORS =' in test_output.stdout:
                print(test_output.stdout)
                self.unit_test_messages.append({"role": "user", "content": f"the unit test returned {self.remove_unnecessary_text(test_output.stdout)}, redo the full code replacement of unit test\
                                                    so I can put your answer in the file and run the pytest, dont ask me to change anything\
                                                , do not just give me the corrected part"})
                unit_test_code, self.unit_test_messages = self.chat_gpt_wrapper(input_messages=self.unit_test_messages)
                if os.path.exists(current_test_path):
                    os.remove(current_test_path)
                with open(current_test_path, "w") as test_f:
                    test_f.write(unit_test_code)
                test_output = subprocess.run(command,capture_output=True, text=True)
            else:
                break
            minimum_test_failure-=1
        else:
            print('min_test_failed')

    def method_function_processor(self, class_name: Optional[str] = None, function_name: str = '', func_str: str = '') -> None:
        """
        Processes the given function string based on the configuration settings.

        Args:
            class_name (Optional[str], default=None): The name of the class the function belongs to, if any.
            function_name (str, default=''): The name of the function.
            func_str (str, default=''): The function string to be processed.

        Returns:
            None
        """
        self.class_name = None
        self.class_part = None
        if class_name:
            self.class_name = str(class_name).split('.')[1].split("'")[0]
            self.class_part = 'in class ' + str(class_name).split('.')[1].split("'")[0] if class_name else None
        if self.config['document']:
            self.documenter(func_str=func_str,class_name=class_name)
        if self.config['unit_test']:
            if class_name:
                self.unit_tester(func_str=func_str, function_name=function_name, class_obj=class_name)
            else:
                self.unit_tester(func_str=func_str, function_name=function_name)
        if self.config['conversion']:
            self.converter(func_str=func_str)

    def object_processor(self, obj_key, obj_value):
        if type(obj_value) == dict:
            for method_name, class_method in obj_value.items():
                self.method_function_processor(
                    class_name=obj_key, function_name=method_name, func_str=class_method)
        else:
            function_name = obj_key
            self.method_function_processor(
                class_name=None, function_name=function_name, func_str=obj_value)

    # Other methods and attributes here...

    def main_pipeline(
        self,
        repo_explanation: str = '',
        directory: str = '',  # path to the entire repo folder
        unit_test_package: str = "pytest",
        doc_package: str = "sphinx",
        platform: str = "Python 3.9",
    ) -> None:
        """
        Pipeline to generate unit test for all code files that contain modules in a directory.

        Args:
            repo_explanation (str, optional): High level explanation of what the project does and what needs to have unit test generated.
            directory (str, optional): Path to the entire repo folder, default to config directory.
            unit_test_package (str, optional): Unit test package to use, default is "pytest".
            doc_package (str, optional): Documentation package to use, default is "sphinx".
            platform (str, optional): Platform to use, default is "Python 3.9".

        Examples:
            >>> code_toolbox = CodeToolbox()
            >>> code_toolbox.main_pipeline(repo_explanation="This project is a simple calculator.", directory="path/to/repo")
        """
        if not repo_explanation:
            self.repo_explanation = self.config['repo_explanation']
        if not directory:
            self.directory=self.config['directory']
        # TODO: in current way, you cannot do java or something else with python. change platform and unit_test_package maybe.

        self.object_dict = {}
        self.directory_dict = {}
        self.object_dict, self.directory_dict = import_all_modules(
            directory=self.directory, object_dict=self.object_dict, directory_dict=self.directory_dict
        )

        if os.path.exists("current_modules.json"):
            with open("current_modules.json", "r") as current_file:
                self.current_data = json.load(current_file)

        if os.path.exists("previous_modules.json"):
            with open("previous_modules.json", "r") as previous_file:
                self.previous_data = json.load(previous_file)
        else:
            self.previous_data = None

        # loop through all files in the current repo
        for self.file_path, objects in self.object_dict.items():
            if "objects" in objects:
                if not os.path.exists(
                    "current_modules.json"
                ):  # this is the first push, so all unit tests, documents need to be generated (no modification/ deletion)
                    for obj_key, obj_value in objects["objects"].items():
                        if obj_value:
                            self.object_processor(obj_key, obj_value)
                # check if file already exists before push
                elif os.path.exists("previous_modules.json"):
                    # file does not exist previous, meaning this file is newly created so whole new unit tests need to be generated
                    if self.file_path not in self.previous_data:
                        for obj_key, obj_value in objects["objects"].items():
                            if obj_value:
                                self.object_processor(obj_key, obj_value)
                    else:
                        # if file exists previously
                        # detect the class/ function that got modified and regenerate unit test
                        # loop through all objects in file to detect the changes
                        for obj_key, obj_value in objects["objects"].items():
                            if obj_value:
                                class_name = None
                                function_name = ""
                                if type(obj_value) == dict:  # file has class and functions
                                    for class_method_name, class_method in obj_value.items():
                                        class_name = str(class_method).split(".")[
                                            0].split(" ")[1]
                                        function_name = str(class_method).split(".")[
                                            1].split(" ")[0]
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
                                else:  # file only has functions
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
                else:  # when `current_modules.json` exist but `previous_modules.json` doesn't exist
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
                        # loop through objects to delete certain object
                        if "objects" in self.current_data[self.previous_file_path]:
                            for obj_key, obj_value in objects["objects"].items():
                                if obj_value:
                                    if obj_key in self.current_data[self.previous_file_path]["objects"]:
                                        if type(obj_value) == dict:
                                            if type(self.current_data[self.previous_file_path]["objects"][obj_key]) == dict:
                                                for class_method_name, class_method in obj_value.items():
                                                    class_name = str(class_method).split(".")[
                                                        0].split(" ")[1]
                                                    function_name = str(class_method).split(".")[
                                                        1].split(" ")[0]
                                                    if class_method_name not in self.current_data[self.previous_file_path]["objects"][obj_key][obj_value]:
                                                        self.delete_unit_test_file_for_each_function(
                                                            class_name, function_name)
                                                    else:
                                                        if class_method not in self.current_data[self.previous_file_path]["objects"][obj_key][obj_value][class_method_name]:
                                                            self.delete_unit_test_file_for_each_function(
                                                                class_name, function_name)
                                            else:
                                                for class_method_name, class_method in obj_value.items():
                                                    class_name = str(class_method).split(".")[
                                                        0].split(" ")[1]
                                                    function_name = str(class_method).split(".")[
                                                        1].split(" ")[0]
                                                    self.delete_unit_test_file_for_each_function(
                                                        class_name, function_name)
                                        else:
                                            if obj_value in self.current_data[self.previous_file_path]["objects"][obj_key]:
                                                class_name = None
                                                function_name = obj_key
                                                self.delete_unit_test_file_for_each_function(
                                                    class_name, function_name)
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
        converted_object_dict = self.convert_keys_to_str(self.object_dict)
        with open("current_modules.json", "w") as file:
            json.dump(converted_object_dict, file, indent=4)
        # Implementation of the method here...

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
    code_toolbox = CodeToolbox(config_path='code_toolbox_config.yaml')

    code_toolbox.main_pipeline()
    # print(code_toolbox.main_pipeline())
