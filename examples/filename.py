import os
import csv

def get_notebook_files(directory):
    notebook_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.ipynb'):
                # Extract the file name without the extension
                file_name = os.path.splitext(file)[0]
                notebook_files.append(file_name)
    return notebook_files

# Specify the path to your 'examples' directory
directory_path = 'examples'
notebook_files = get_notebook_files(directory_path)

# Save the notebook files to a CSV
csv_file_path = 'notebook_files.csv'
with open(csv_file_path, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    for notebook_file in notebook_files:
        writer.writerow([notebook_file])