import os
import cohere
import csv
from dotenv import load_dotenv

load_dotenv()
COHERE_API_KEY = os.getenv('COHERE_API_KEY')
co = cohere.Client(COHERE_API_KEY)

documents = []

with open('data/noc.csv', newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        id = row['Code - NOC 2021 V1.0']
        record = {
            'id': id, 
            'title': row['Class title'],
            'snippet': 'id="' + id + '": ' + row['Class definition']
        }
        documents.append(record)

def include_page(document):
    return document['id'].startswith('62')

selected_documents = [d for d in documents if include_page(d)]

admin_assistant_js = ("As an Administrative Assistant in the film industry, you will play a pivotal  " + 
                          "role in supporting the administrative and organizational functions of film " +
                           "production companies, studios, or related entities. You will be responsible for " +
                           " providing comprehensive administrative support to ensure smooth operations and " +
                           " facilitate the execution of various projects within the dynamic and fast-paced " +
                           " environment of the film industry.'");

hospital_chef_jd = ("Title: Hospital Chef\n" +
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

result = co.chat(
  model='command',
  message='Which of the provided documents most closely match this job description: "' + hospital_chef_jd + '", include the corresponding ids in the response',
  documents=selected_documents)

print(40*'*')
print(result.message)
print(40*'*')
print(result.text)
print(40*'*')
