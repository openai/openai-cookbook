from langchain_community.document_loaders import WebBaseLoader
from langchain_community.vectorstores import Chroma
from langchain_community import embeddings
from langchain_community.chat_models import ChatOllama
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain.docstore.document import Document
import csv
import json
import time
import os.path

# langchain UI tool

t1 = time.time()
noc_codes = []

with open('data/noc.csv', newline='') as csvfile:
    noc_codes = [
        { 'code': row['Code - NOC 2021 V1.0'], 'title': row['Class title'], 'definition': row['Class definition'] } 
        for row in csv.DictReader(csvfile)
    ]

# Filter out duplicate codes
def include_code(row):
    return row['code'] not in ['11', '1', '0', '14', '12', '13', '10' ]

filtered_noc_codes = [code for code in noc_codes if include_code(code)]

def to_page_content(code):
    return json.dumps(code)

documents = [Document(page_content=to_page_content(code)) for code in filtered_noc_codes]
print('total documents included = ', len(documents))

# Sources
# https://www.youtube.com/watch?v=jENqvjpkwmw

model_local = ChatOllama(model="mistral")

# TODO don't build the vectors each time, store in a vector database, this needs to be persisted, maybe local redis

def load_embeddings():
    return Chroma(
        collection_name="rag-chroma",
        embedding_function=embeddings.ollama.OllamaEmbeddings(model='nomic-embed-text'),
        persist_directory="./chroma_db"
    )

def compute_embeddings():
    return Chroma.from_documents(
        documents=documents,
        collection_name="rag-chroma",
        embedding=embeddings.ollama.OllamaEmbeddings(model='nomic-embed-text'),
        persist_directory="./chroma_db"
    )

def load_or_compute_embeddings():
    embeddings_exist = os.path.isfile("./chroma_db/chroma.sqlite3")
    return load_embeddings() if embeddings_exist else compute_embeddings()

embeddings = load_or_compute_embeddings()

t2 = time.time()
print('Documents loaded in ' + str(t2 - t1) + ' seconds')

t1 = time.time()

retriever = embeddings.as_retriever()

print('H1: ' + str(time.time() - t1) + ' seconds')

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

print('H2: ' + str(time.time() - t1) + ' seconds')

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

geological_engineer_jd = ("""Title: Geological Engineer

Job Summary:
As a Geological Engineer, you will play a crucial role in assessing the geological conditions of sites and providing expertise in engineering projects related to natural resources exploration, environmental protection, infrastructure development, and hazard mitigation. Your responsibilities will involve analyzing geological data, conducting field surveys, and collaborating with multidisciplinary teams to ensure the safe and efficient execution of engineering projects.

Responsibilities:
1. **Site Investigation:** Conduct geological surveys and site investigations to assess geological features, including rock formations, soil composition, groundwater conditions, and potential hazards such as landslides, earthquakes, or sinkholes.
2. **Geological Mapping:** Create detailed geological maps and models using specialized software and mapping techniques to identify geological structures, mineral deposits, and potential risks for engineering projects.
3. **Geotechnical Analysis:** Perform geotechnical analyses to evaluate soil stability, bearing capacity, and slope stability for the design and construction of infrastructure projects, such as buildings, bridges, roads, and dams.
4. **Risk Assessment:** Assess geological risks and hazards associated with engineering projects, including seismic activity, soil erosion, groundwater contamination, and geological instabilities, and develop mitigation strategies to minimize risks.
5. **Environmental Impact Assessment:** Evaluate the environmental impact of engineering activities on natural ecosystems, water resources, and air quality, and recommend measures to mitigate negative impacts and ensure compliance with environmental regulations.
6. **Resource Exploration:** Assist in the exploration and extraction of natural resources, such as minerals, oil, gas, and water, by analyzing geological data, conducting drilling surveys, and identifying potential resource reserves.
7. **Project Planning:** Provide geological input and expertise during the planning and design phases of engineering projects, including site selection, foundation design, and construction techniques, to optimize project outcomes and minimize geological risks.
8. **Data Analysis:** Analyze geological data collected from field surveys, laboratory tests, and remote sensing""")

print('H3: ' + str(time.time() - t1) + ' seconds')

# TODO make system prompt and user prompt
print(after_rag_chain.invoke("What are the three documents that most closely match this job description: '" + geological_engineer_jd + "'. Answer in JSON format with the top level identifier 'results', and attributes code, title, definition, score and comment for each matching document, where score is a number between 0 and 1 indicating how close the match is to the job description, with 1 meaning really close, and comment explains why each documents was selected as a good match."))

print('Results ready in ' + str(time.time() - t1) + ' seconds')
