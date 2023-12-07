llm = OpenAI()
qa = VectorDBQA.from_chain_type(
    llm=llm, 
    chain_type="stuff", 
    vectorstore=doc_store,
    return_source_documents=False,
)