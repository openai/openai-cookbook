# Set user root directory to the 'openai-python' repository
root_dir = Path.home()

# Assumes the 'openai-python' repository exists in the user's root directory
code_root = root_dir / 'openai-python'

# Extract all functions from the repository
all_funcs = extract_functions_from_repo(code_root)