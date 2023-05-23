**[SingleStoreDB](https://singlestore.com)** has first-class support for vector search through our [Vector Functions](https://docs.singlestore.com/managed-service/en/reference/sql-reference/vector-functions.html). Our vector database subsystem, first made available in 2017 and subsequently enhanced, allows extremely fast nearest-neighbor search to find objects that are semantically similar, easily using SQL.

SingleStoreDB supports vectors and vector similarity search using dot_product (for cosine similarity) and euclidean_distance functions. These functions are used by our customers for applications including face recognition, visual product photo search and text-based semantic search. With the explosion of generative AI technology, these capabilities form a firm foundation for text-based AI chatbots.

But remember, SingleStoreDB is a high-performance, scalable, modern SQL DBMS that supports multiple data models including structured data, semi-structured data based on JSON, time-series, full text, spatial, key-value and of course vector data. Start powering your next intelligent application with SingleStoreDB today!

![SingleStore Open AI](https://user-images.githubusercontent.com/8846480/236985121-48980956-fdc5-49c8-b006-f3a412142676.png)

## Example

This folder contains examples of using SingleStoreDB and OpenAI together. We will keep adding more scenarios so stay tuned!

| Name | Description |
| --- | --- |
| [OpenAI wikipedia semantic search](./OpenAI_wikipedia_semantic_search.ipynb) | Improve ChatGPT accuracy through SingleStoreDB semantic Search in QA |
