import textract
import os
import openai
import tiktoken

# Extract the raw text from each PDF using textract
text = textract.process('data/fia_f1_power_unit_financial_regulations_issue_1_-_2022-08-16.pdf', method='pdfminer').decode('utf-8')
clean_text = text.replace("  ", " ").replace("\n", "; ").replace(';',' ')