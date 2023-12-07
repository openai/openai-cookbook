from langchain.chains import RetrievalQA

retrieval_llm = OpenAI(temperature=0)

podcast_retriever = RetrievalQA.from_chain_type(llm=retrieval_llm, chain_type="stuff", retriever=docsearch.as_retriever())