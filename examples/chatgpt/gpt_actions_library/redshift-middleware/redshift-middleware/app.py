import json
import psycopg2
import os
import base64
import tempfile
import csv

# Fetch Redshift credentials from environment variables
host = os.environ['REDSHIFT_HOST']
port = os.environ['REDSHIFT_PORT']
user = os.environ['REDSHIFT_USER']
password = os.environ['REDSHIFT_PASSWORD']
database = os.environ['REDSHIFT_DB']

def execute_statement(sql_statement):
    try:
        # Establish connection
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=database
        )
        cur = conn.cursor()
        cur.execute(sql_statement)
        conn.commit()

        # Fetch all results
        if cur.description:
            columns = [desc[0] for desc in cur.description]
            result = cur.fetchall()
        else:
            columns = []
            result = []

        cur.close()
        conn.close()
        return columns, result

    except Exception as e:
        raise Exception(f"Database query failed: {str(e)}")

def lambda_handler(event, context):
    try:
        data = json.loads(event['body'])
        sql_statement = data['sql_statement']

        # Execute the statement and fetch results
        columns, result = execute_statement(sql_statement)
        
        # Create a temporary file to save the result as CSV
        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.csv', newline='') as tmp_file:
            csv_writer = csv.writer(tmp_file)
            if columns:
                csv_writer.writerow(columns)  # Write the header
            csv_writer.writerows(result)  # Write all rows
            tmp_file_path = tmp_file.name

        # Read the file and encode its content to base64
        with open(tmp_file_path, 'rb') as f:
            file_content = f.read()
            encoded_content = base64.b64encode(file_content).decode('utf-8')

        response = {
            'openaiFileResponse': [
                {
                    'name': 'query_result.csv',
                    'mime_type': 'text/csv',
                    'content': encoded_content
                }
            ]
        }

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps(response)
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
