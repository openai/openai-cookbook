# Execute this query to test the database connection
cursor.execute("SELECT 1;")
result = cursor.fetchone()

# Check the query result
if result == (1,):
    print("Your database connection was successful!")
else:
    print("Your connection failed.")