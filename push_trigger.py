import json
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
            new_dict[new_key] = value.__qualname__  # Convert function object to qualified name
        else:
            new_dict[new_key] = value
    return new_dict


def has_function_changed(current_file, previous_file, function_name):
    """
    Check if a function has changed between current and previous versions of the file.
    """
    current_data = json.load(current_file)
    previous_data = json.load(previous_file)

    current_function = current_data[function_name]
    previous_function = previous_data[function_name]

    return current_function != previous_function


object_dict = {}
directory_dict = {}
object_dict, directory_dict = import_all_modules(
    directory="test_code", object_dict=object_dict, directory_dict=directory_dict
)
converted_object_dict = convert_keys_to_str(object_dict)
# converted_object_dict = {str(key): value for key, value in object_dict.items()}
# Save the current state to current_modules.json
with open("current_modules.json", "w") as file:
    json.dump(converted_object_dict, file, indent=4)

# Load current and previous versions of the file
with open('current_modules.json', 'r') as current_file, open('previous_modules.json', 'r') as previous_file:
    function_name = 'test_code\\dq_utility.py.objects[<class \'test_code\\dq_utility.DataCheck\'>].add_error_col'
    function_changed = has_function_changed(current_file, previous_file, function_name)

if function_changed:
    print(f"The function {function_name} has changed.")
else:
    print(f"The function {function_name} has not changed.")
