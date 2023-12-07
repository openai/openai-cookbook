result_list = []

for result in search.results():
    result_dict = {}

    result_dict.update({"title": result.title})
    result_dict.update({"summary": result.summary})

    # Taking the first url provided
    result_dict.update({"article_url": [x.href for x in result.links][0]})
    result_dict.update({"pdf_url": [x.href for x in result.links][1]})
    result_list.append(result_dict)