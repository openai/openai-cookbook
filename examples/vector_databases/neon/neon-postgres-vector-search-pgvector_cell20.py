# Check the size of the data
count_sql = """select count(*) from public.articles;"""
cursor.execute(count_sql)
result = cursor.fetchone()
print(f"Count:{result[0]}")