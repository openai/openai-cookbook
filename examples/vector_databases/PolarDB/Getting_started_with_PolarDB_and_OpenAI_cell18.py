# Check the collection size to make sure all the points have been stored
count_sql = """select count(*) from public.articles;"""
cursor.execute(count_sql)
result = cursor.fetchone()
print(f"Count:{result[0]}")