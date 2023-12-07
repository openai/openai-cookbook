output_list = []
for x in result_list:
    content = x["title"] + ": " + x["summary"]

    try:
        output_list.append(document_relevance(query, document=content))

    except Exception as e:
        print(e)