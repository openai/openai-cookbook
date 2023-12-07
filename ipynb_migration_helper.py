import argparse
import os
import json
import re

# Migration helper script for Jupyter Notebooks
# Extracts code cells from .ipynb files into .py files
# Reinserts code cells from .py files into .ipynb files when using --reinsert
# Usage
#    $ python ipynb_migration_helper.py <directory> [--reinsert]

# Process: 
# 1. Extract code cells from .ipynb files into .py files
#    $ python ipynb_migration_helper.py examples
# 2. Apply openai migrate
#    $ openai migrate
# 3. Reinsert code cells from .py files into .ipynb files
#    $ python ipynb_migration_helper.py examples --reinsert

def extract_code_from_ipynb(ipynb_path, output_dir):
    # Extracts code cells from .ipynb files into .py files
    with open(ipynb_path, 'r') as file:
        notebook = json.load(file)

    base_name = os.path.splitext(os.path.basename(ipynb_path))[0]

    for index, cell in enumerate(notebook.get('cells', [])):
        if cell.get('cell_type') == 'code':
            code = ''.join(cell.get('source', []))
            cell_name = cell.get('metadata', {}).get('name', f'cell{index}')
            output_path = os.path.join(output_dir, f'{base_name}_{cell_name}.py')

            with open(output_path, 'w') as code_file:
                code_file.write(code)

def extract_notebook_cells(directory):
    # Extracts code cells from .ipynb files into .py files
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.ipynb'):
                extract_code_from_ipynb(os.path.join(root, file), root)


def detect_indentation_style(file_descriptor):
    """Detect the indentation style (number of spaces or tabs) from the file descriptor."""
    original_position = file_descriptor.tell()
    file_descriptor.seek(0)
    lines = file_descriptor.readlines()
    file_descriptor.seek(original_position)  # Reset the position to the original

    for line in lines:
        match = re.match(r'^\s+', line)
        if match:
            return len(match.group(0))

    return -1 # some notebooks don't have any intentation

def reinsert_notebook_cells(directory):
    # Reinserts code cells from .py files into .ipynb files
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.ipynb'):
                notebook_path = os.path.join(root, file)
                base_name = os.path.splitext(os.path.basename(notebook_path))[0]

                # Detect indentation style so we can match it
                with open(notebook_path, 'r') as notebook_file:
                    indent_level = detect_indentation_style(notebook_file)

                # Read file content
                with open(notebook_path, 'rb') as notebook_file:
                    notebook_original_content = notebook_file.read()

                notebook = json.loads(notebook_original_content)

                for index, cell in enumerate(notebook.get('cells', [])):
                    if cell.get('cell_type') == 'code':
                        cell_name = cell.get('metadata', {}).get('name', f'cell{index}')
                        code_file_path = os.path.join(root, f'{base_name}_{cell_name}.py')

                        if os.path.exists(code_file_path):
                            with open(code_file_path, 'r') as code_file:
                                cell['source'] = code_file.readlines()

                            os.remove(code_file_path)  # Cleanup: Delete the _cellX.py file

                with open(notebook_path, 'w') as notebook_file:
                    notebook_file.write(json.dumps(notebook, indent=indent_level, ensure_ascii=False) + '\n')

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Process Jupyter Notebooks')
    parser.add_argument('directory', type=str, help='Directory to search for .ipynb files')
    parser.add_argument('--reinsert', action='store_true', help='Reinsert code cells into notebooks')
    args = parser.parse_args()

    if args.reinsert:
        # Reinsert code cells into notebooks
        reinsert_notebook_cells(args.directory)
    else:
        # Extract code cells from notebooks
        extract_notebook_cells(args.directory)
