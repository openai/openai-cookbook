import openai
import numpy as np

query_result = query_tair(client=client, query="modern art in Europe", vector_name="title_vector")
for i in range(len(query_result)):
    title = client.tvs_hmget(index+"_"+"content_vector", query_result[i][0].decode('utf-8'), "title")
    print(f"{i + 1}. {title[0].decode('utf-8')} (Distance: {round(query_result[i][1],3)})")