# Create database
stmt = """
    CREATE DATABASE IF NOT EXISTS winter_wikipedia2;
"""

cur.execute(stmt)
