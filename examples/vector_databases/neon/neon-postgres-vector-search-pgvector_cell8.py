import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# The connection string can be provided directly here.
# Replace the next line with Your Neon connection string.
connection_string = "postgres://<user>:<password>@<hostname>/<dbname>"

# If connection_string is not directly provided above, 
# then check if DATABASE_URL is set in the environment or .env.
if not connection_string:
    connection_string = os.environ.get("DATABASE_URL")

    # If neither method provides a connection string, raise an error.
    if not connection_string:
        raise ValueError("Please provide a valid connection string either in the code or in the .env file as DATABASE_URL.")

# Connect using the connection string
connection = psycopg2.connect(connection_string)

# Create a new cursor object
cursor = connection.cursor()