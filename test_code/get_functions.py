import os
import importlib
import inspect
from typing import List, Tuple, Any

def getmembers(item: Any, predicate=None) -> List[Tuple[str, Any]]:
    """
    Get all members of an object.

    :param item: An object to get the members of.
    :param predicate: A callable used to filter the members.
    :return: A list of tuples containing the name and value of each member.
    """
    if predicate is None:
        predicate = inspect.ismemberdescriptor
    return inspect.getmembers(item, predicate)

def import_all_modules(directory: str,output_dict) -> None:
    """
    Import all modules from a directory.

    :param directory: The directory to import modules from.
    :return: None
    """
    
    for file in os.listdir(directory):
        
        filepath = os.path.join(directory, file)
        if os.path.isdir(filepath):
            # Recursively call the function for subdirectories
            import_all_modules(filepath,output_dict)
        elif file.endswith(".py") and file != '__init__.py':
            print(file)
            module_name = file[:-3]
            spec = importlib.util.spec_from_file_location(module_name, os.path.join(directory, file))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            members = getmembers(module, inspect.isfunction)
            for member in members:
                if member[1].__module__ == module.__name__:
                    # print(f"Function name: {member[0]}")
                    # print(f"Function definition: {inspect.getsource(member[1])}")
                    # print("------------")
                    output_dict[member[0]]=inspect.getsource(member[1])
                # else:
                    # print(f"Skipping imported function: {member[0]}")
            classes = [m[1] for m in getmembers(module, inspect.isclass)]
            for class_ in classes:
                members = getmembers(class_, inspect.isfunction)
                for member in members:
                    if member[1].__module__ == module.__name__:
                        # print(f"Method name: {member[0]}")
                        # print(f"Method definition: {inspect.getsource(member[1])}")
                        # print("------------")
                        output_dict[member[0]]=inspect.getsource(member[1])
                    # else:
                        # print(f"Skipping imported method: {member[0]}")
    return output_dict

if __name__ == "__main__":
    output_dict={}
    output_dict=import_all_modules(".",output_dict)
    print(output_dict)