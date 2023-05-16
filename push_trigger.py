import dill
import json
import inspect
from get_functions import import_all_modules

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

def serialize_function_dict(dictionary):
    serialized_function_dict = {}
    for key, value in dictionary.items():
        try:
            # Attempt to serialize the function
            serialized_function = dill.dumps(value)
            serialized_function_dict[key] = serialized_function
        except TypeError:
            # Handle the TypeError (e.g., exclude SSLContext)
            print(f"Skipping serialization for function: {key}")
    return serialized_function_dict

def deserialize_function_objects(dictionary):
    # Deserialize the function objects
    function_dict = {}

    for key, value in dictionary.items():
        try:
            # Attempt to deserialize the function
            function = dill.loads(value)
            function_dict[key] = function
        except Exception as e:
            print(f"Error deserializing function: {key}")
            print(f"Error message: {str(e)}")
    return function_dict

# def object_processor(obj_key, obj_value):
#     if type(obj_value) == dict:
#         print(obj_value)
#         for class_method_name, class_method in obj_value.items():
#             class_name = str(class_method).split(".")[0].split(" ")[1]
#             function_name = str(class_method).split(".")[1].split(" ")[0]
#             function_to_test = inspect.getsource(class_method)
#     else:
#         function_name = obj_key
#         function_to_test = inspect.getsource(obj_value)
#         # print(function_name)

def has_function_changed(current_file, previous_file, function_name):
    """
    Check if a function has changed between current and previous versions of the file.
    """
    current_data = json.load(current_file)
    previous_data = json.load(previous_file)

    # for file_path, objects in current_data.items():
    #     if "objects" in objects:
    #         for obj_key, obj_value in objects["objects"].items():
    #             if obj_value:
    #                 object_processor(obj_key,obj_value)
    # current_data = deserialize_function_objects(serialized_current_data)
    # previous_data = deserialize_function_objects(serialized_previous_data)

    current_function= current_data['test_code\\dq_utility.py']['objects']["<class \'test_code\\dq_utility.DataCheck\'>"][function_name]
    previous_function = previous_data['test_code\\dq_utility.py']['objects']["<class \'test_code\\dq_utility.DataCheck\'>"][function_name]

    # current_function = getattr(eval(current_class), current_function_str)
    # previous_function = getattr(eval(current_class), previous_function_str)

    # current_hash = hashlib.md5(current_function.encode()).hexdigest()
    # previous_hash = hashlib.md5(previous_function.encode()).hexdigest()
    # current_function_code = inspect.getsource(current_function)
    # print(current_function_code)
    # previous_function_code = inspect.getsource(previous_function)
    # print(previous_function_code)

    return current_function != previous_function


object_dict = {}
directory_dict = {}
object_dict, directory_dict = import_all_modules(
    directory="test_code", object_dict=object_dict, directory_dict=directory_dict
)

converted_object_dict = convert_keys_to_str(object_dict)
# converted_object_dict = {str(key): value for key, value in object_dict.items()}

# Serialize the function dictionary
# serialized_object_dict = serialize_function_dict(object_dict)

# Save the current state to current_modules.json
with open("current_modules.json", "w") as file:
    json.dump(converted_object_dict, file, indent=4)

# Load current and previous versions of the file
with open('current_modules.json', 'r') as current_file, open('previous_modules.json', 'r') as previous_file:
    function_name = 'add_error_col'
    function_changed = has_function_changed(current_file, previous_file, function_name)

if function_changed:
    print(f"The function {function_name} has changed.")
else:
    print(f"The function {function_name} has not changed.")

# with open('current_modules.json', 'r') as current_file, open('previous_modules.json', 'r') as previous_file:
    # current_data = json.load(current_file)
    # previous_data = json.load(previous_file)

# current_data = object_dict
# for file_path, objects in current_data.items():
#     if "objects" in objects:
#         for obj_key, obj_value in objects["objects"].items():
#             if obj_value:
#                 object_processor(obj_key,obj_value)

# current_class = "<class \'test_code\\dq_utility.DataCheck\'>"
# current_function_str = current_data['test_code\\dq_utility.py']['objects']["<class \'test_code\\dq_utility.DataCheck\'>"][function_name]
# previous_function_str = previous_data['test_code\\dq_utility.py']['objects']["<class \'test_code\\dq_utility.DataCheck\'>"][function_name]
