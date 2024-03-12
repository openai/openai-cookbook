from langchain_community.document_loaders import WebBaseLoader
from langchain_community.vectorstores import Chroma
from langchain_community import embeddings
from langchain_community.chat_models import ChatOllama
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain.text_splitter import CharacterTextSplitter
from langchain.docstore.document import Document
import csv

noc_data = []

with open('data/noc.csv', newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        record = {
            'code': row['Code - NOC 2021 V1.0'], 
            'title': row['Class title'],
            'definition': row['Class definition']
        }
        noc_data.append(record)

def include_page(page):
    return True # page['code'].startswith('5')

def to_page_content(page):
    return 'code="' + page['code'] + '" title="' + page['title'] + '" definition="' + page['definition'] + '"'

docs = [[Document(page_content=to_page_content(page)) for page in noc_data if include_page(page)]]



# Sources
# https://www.youtube.com/watch?v=jENqvjpkwmw

model_local = ChatOllama(model="mistral")

# 1. Split data into chucks
urls = [
    "https://ollama.com",
    "https://ollama.com/blog/windows-preview",
    "https://ollama.com/blog/openai-compatibility",
]

# docs = [WebBaseLoader(url).load() for url in urls];

flattened_docs = [item for sublist in docs for item in sublist]
print(flattened_docs)
print('total documents included = ', len(flattened_docs))
text_splitter = CharacterTextSplitter.from_tiktoken_encoder(chunk_size=7500, chunk_overlap=100)
doc_splits = text_splitter.split_documents(flattened_docs)

# 2. Convert documents to Embeddings and store them
vectorstore = Chroma.from_documents(
    documents=doc_splits,
    collection_name="rag-chroma",
    embedding=embeddings.ollama.OllamaEmbeddings(model='nomic-embed-text')
)

retriever = vectorstore.as_retriever()

# 3. Before RAG
print("Before RAG\n")
before_rag_template = "What is {topic}"
before_rag_prompt = ChatPromptTemplate.from_template(before_rag_template)
before_rag_chain = before_rag_prompt | model_local | StrOutputParser()
print(before_rag_chain.invoke({"topic" : "trademark agents"}))

# 4. After rAG
print("\n###########\nAfter RAG")
after_rag_template = """Answer the question based only on the following context:
{context}
Question: {question}
"""
after_rag_prompt = ChatPromptTemplate.from_template(after_rag_template)
after_rag_chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | after_rag_prompt
    | model_local
    | StrOutputParser()
)

admin_assistant_js = ("As an Administrative Assistant in the film industry, you will play a pivotal  " + 
                             "role in supporting the administrative and organizational functions of film " +
                             "production companies, studios, or related entities. You will be responsible for " +
                             " providing comprehensive administrative support to ensure smooth operations and " +
                             " facilitate the execution of various projects within the dynamic and fast-paced " +
                             " environment of the film industry.'");

hopital_chef_jd = ("Title: Hospital Chef\n" +
"Job Summary:\n" +
"As a Hospital Chef, you will play a vital role in ensuring the provision of high-quality, nutritious meals for patients, \n" +
"staff, and visitors in a healthcare setting. Working closely with dietitians, nutritionists, and culinary staff, you\n" +
" will be responsible for planning, preparing, and overseeing the production of meals that meet dietary requirements,\n" +
" taste preferences, and nutritional standards.\n" +
"Responsibilities:\n" +
"1. **Menu Planning:** Collaborate with dietitians and nutritionists to plan menus that meet the dietary needs of patients\n" +
" while adhering to medical guidelines and dietary restrictions.\n" +
"2. **Food Preparation:** Prepare and cook meals according to standardized recipes, ensuring consistency in taste, \n" +
"presentation, and portion sizes. Monitor food quality and taste to maintain high standards.\n" +
"3. **Nutritional Considerations:** Ensure that meals are balanced, nutritious, and appropriate for patients with\n" +
" specific medical conditions or dietary restrictions, such as diabetes, food allergies, or heart disease.\n" +
"4. **Food Safety and Sanitation:** Adhere to strict food safety and sanitation protocols to prevent contamination and \n" +
"ensure compliance with health regulations. Monitor kitchen hygiene, equipment maintenance, and food storage practices.\n" +
"5. **Inventory Management:** Oversee inventory levels of food and kitchen supplies, ordering ingredients and supplies \n" +
"as needed to maintain stock levels and minimize waste. Monitor food costs and budgetary constraints.\n" +
"6. **Team Leadership:** Supervise kitchen staff, including cooks, sous chefs, and kitchen assistants, providing \n" +
"guidance, training, and support to ensure efficient operations and teamwork.\n" +
"7. **Special Dietary Needs:** Accommodate special dietary requests from patients, staff, and visitors, \n" +
"including vegetarian, vegan, gluten-free, and other dietary preferences or restrictions.\n" +
"8. **Menu Development:** Continuously evaluate and update menus to incorporate seasonal ingredients, culinary\n" +
" trends, and feedback from patients and staff. Introduce new recipes and dishes to enhance the dining experience.\n" +
"9. **Patient Satisfaction:** Solicit feedback from patients and staff regarding meal quality, preferences,\n" +
" and satisfaction. Implement improvements and adjustments based on feedback to enhance the overall dining experience.\n" +
"10. **Regulatory Compliance:** Ensure compliance with regulatory agencies, such as the Department of Health, Joint Commission, and local health authorities")


print(after_rag_chain.invoke("What is the title and code of the document that most closely matches this job description: '" + hopital_chef_jd + "'"))
