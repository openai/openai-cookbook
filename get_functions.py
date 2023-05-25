import inspect
import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import ast
import importlib
import csv

def recursive_items(dictionary: Dict[str, Union[str, Dict[str, Any]]]) -> Union[str, Tuple[str, Union[str, Dict[str, Any]]]]:
    """
    Recursively iterates through a dictionary and returns the key-value pairs.

    Args:
        dictionary (Dict[str, Union[str, Dict[str, Any]]]): The input dictionary.

    Returns:
        Union[str, Tuple[str, Union[str, Dict[str, Any]]]]: The key-value pairs found in the dictionary.

    Examples:
        >>> recursive_items({"a": 1, "b": {"c": 2, "d": 3}})
        ('a', 1), ('b', {'c': 2, 'd': 3})
    """
    for key, value in dictionary.items():
        if type(value) is dict:
            if value:
                return key + "," + "".join(recursive_items(value))
            else:
                return (key, value)
        else:
            return (key, value)

def getmembers(item: Any, predicate: Optional[Callable] = None) -> List[Tuple[str, Any]]:
    """
    Get all members of an object.

    Args:
        item (Any): An object to get the members of.
        predicate (Callable, optional): A callable used to filter the members. Defaults to None.

    Returns:
        List[Tuple[str, Any]]: A list of tuples containing the name and value of each member.
    """
    if predicate is None:
        predicate = inspect.ismemberdescriptor
    return inspect.getmembers(item, predicate)

def import_modules_from_file(filepath: str, extension: str, object_dict: Dict[str, Any], directory_dict: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Imports modules from a file and updates the object_dict and directory_dict with the imported data.

    Args:
        filepath (str): The path to the file.
        extension (str): The file extension (e.g., ".json", ".csv", ".py").
        object_dict (dict): A dictionary to store the imported objects.
        directory_dict (dict): A dictionary to store the directory information.

    Returns:
        Tuple[dict, dict]: A tuple containing the updated object_dict and directory_dict.

    Examples:
        >>> object_dict = {}
        >>> directory_dict = {}
        >>> import_modules_from_file("example.py", ".py", object_dict, directory_dict)
        ({'example.py': {'objects': {...}, 'import_str': '...'}}, {'example.py': {'objects': {...}, 'functions': [...]}})
    """
    if extension == ".json":
        with open(filepath, "r") as f:
            data = json.load(f)

        # Get the first and second level keys
        keys = set()
        for key1 in data:
            keys.add(key1)
            if isinstance(data[key1], dict):
                for key2 in data[key1]:
                    keys.add(f"{key1}.{key2}")

        # Convert the set of keys to a string
        key_string = "\n".join(keys)
        directory_dict[filepath + "key_string"] = key_string
    elif extension == ".csv":
        # Open the CSV file for reading
        with open(filepath, newline="") as f:
            reader = csv.reader(f)

            # Read the first row of the CSV file, which contains the column names
            column_names = next(reader)

        # Print the column names
        directory_dict[filepath + "column_names"] = column_names
    elif extension == ".py":
        with open(filepath, "r") as f:
            code = f.read()
        object_dict[filepath] = {}
        directory_dict[filepath] = {}
        object_dict[filepath]["objects"] = {}
        directory_dict[filepath]["objects"] = {}
        tree = ast.parse(code)
        import_str = ""
        for node in tree.body:
            if isinstance(node, ast.Import):
                import_str += f"import {', '.join([alias.name for alias in node.names])}"
            elif isinstance(node, ast.ImportFrom):
                import_str += f"from {node.module} import {', '.join([alias.name for alias in node.names])}"
        module_name = filepath.split("/")[-1].split(".")[0]
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        members = getmembers(module, inspect.isfunction)
        for member in members:
            if not "import_str" in object_dict[filepath]:
                object_dict[filepath]["import_str"] = import_str
                directory_dict[filepath]["functions"] = []
            if member[1].__module__ == module.__name__:
                object_dict[filepath]["objects"][member[0]] = inspect.getsource(member[1])
                directory_dict[filepath]["functions"].append(member[0])
        classes = [m[1] for m in getmembers(module, inspect.isclass)]

        for class_ in classes:
            if class_.__module__!=module.__name__:
                continue
            object_dict[filepath]["objects"][class_] = {}
            directory_dict[filepath]["objects"][class_] = []
            members = getmembers(class_, inspect.isfunction)
            for member in members:
                if not "import_str" in object_dict[filepath]:
                    object_dict[filepath]["import_str"] = import_str
                directory_dict[filepath]["objects"][class_].append(member[0])
                object_dict[filepath]["objects"][class_][member[0]] = inspect.getsource(member[1])

                # else:
                # print(f"Skipping imported method: {member[0]}")
    return object_dict, directory_dict

def import_all_modules(directory: str, object_dict: Dict, directory_dict: Dict) -> Tuple[Dict, Dict]:
    """
    Import all modules from a directory.

    Args:
        directory (str): The directory to import modules from.
        object_dict (Dict): The dictionary to store imported objects.
        directory_dict (Dict): The dictionary to store imported directories.

    Returns:
        Tuple[Dict, Dict]: A tuple containing the updated object_dict and directory_dict.

    Examples:
        >>> object_dict, directory_dict = import_all_modules("my_directory", {}, {})
    """

    for current_file in os.listdir(directory):
        if current_file == 'docs':
            continue
        filepath = os.path.join(directory, current_file)
        if os.path.isdir(filepath):
            # Recursively call the function for subdirectories
            import_all_modules(filepath, object_dict, directory_dict)
        elif current_file.endswith(".json"):
            object_dict, directory_dict = import_modules_from_file(
                filepath=filepath, extension=".json", object_dict=object_dict, directory_dict=directory_dict
            )

        elif current_file.endswith(".csv"):
            object_dict, directory_dict = import_modules_from_file(
                filepath=filepath, extension=".csv", object_dict=object_dict, directory_dict=directory_dict
            )

        elif current_file.endswith(".py") and current_file != "__init__.py":
            object_dict, directory_dict = import_modules_from_file(
                filepath=filepath, extension=".py", object_dict=object_dict, directory_dict=directory_dict
            )

    return object_dict, directory_dict

if __name__ == "__main__":
    import json
    def convert_keys_to_str(dictionary):
        """
        Recursively convert dictionary keys to strings.
        """
        new_dict = {}
        for key, value in dictionary.items():
            new_key = str(key)  # Convert key to string
            if isinstance(value, dict):
                new_dict[new_key] = convert_keys_to_str(value)  # Recursively convert nested dictionaries
            else:
                new_dict[new_key] = value
        return new_dict

    output_dict = {}
    directory_dict = {}
    output_dict, directory_dict = import_all_modules("test_code", output_dict, directory_dict)
    # print(output_dict)
    converted_dict = convert_keys_to_str(output_dict)
    # print(converted_dict)
    # print("output_dict: ", output_dict, "\ndirectory_dict :", directory_dict)
    with open('modules.json', 'w') as f:
        json.dump(converted_dict, f)

    # dict = {
    #     # 'test_code/__init__.py': {
    #     #     'key1': 'value1',
    #     #     'key2': 'value2',
    #     #     'key3': 'value3'
    #     # },
    #     # 'test_code/tst.py': {},
    #     'main.py': 'M',
    #     'main': ['M'],
    # }
    # print(recursive_items(dict))
