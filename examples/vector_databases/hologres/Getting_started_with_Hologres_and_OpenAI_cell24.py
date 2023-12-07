import io

# Path to the unzipped CSV file
csv_file_path = '../../data/vector_database_wikipedia_articles_embedded.csv'

# In SQL, arrays are surrounded by {}, rather than []
def process_file(file_path):
    with open(file_path, 'r') as file:
        for line in file:
            # Replace '[' with '{' and ']' with '}'
            modified_line = line.replace('[', '{').replace(']', '}')
            yield modified_line

# Create a StringIO object to store the modified lines
modified_lines = io.StringIO(''.join(list(process_file(csv_file_path))))

# Create the COPY command for the copy_expert method
copy_command = '''
COPY public.articles (id, url, title, content, title_vector, content_vector, vector_id)
FROM STDIN WITH (FORMAT CSV, HEADER true, DELIMITER ',');
'''

# Execute the COPY command using the copy_expert method
cursor.copy_expert(copy_command, modified_lines)