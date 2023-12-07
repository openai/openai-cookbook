# Print out the title and content for the most relevant retrieved documents
print("\n".join(['Title: ' + x.metadata['title'].strip() + '\n\n' + x.page_content + '\n\n' for x in query_docs]))