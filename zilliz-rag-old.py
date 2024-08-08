import csv
import numpy
from pymilvus import MilvusClient

# 1. Create a milvus client
client = MilvusClient(
    uri="https://in03-74c1cff007dcc24.api.gcp-us-west1.zillizcloud.com",
    token="db_74c1cff007dcc24:Qo4]5bLFFUdS1Jts"
)

# 2. Create a user
client.create_user(user_name="user_1", password="P@ssw0rd")



exit()





def read_noc_data():
    filename = 'data/NOC-2021-v1.0/NOCs without TEER.csv'
    with open(filename) as noc_file:
        return [
            {
                'noc_code': str(row['Code - NOC 2021 V1.0 as number']),
                'title': row['Class title'],
                'definition': row['Class definition']
            } for row in csv.DictReader(noc_file)
        ]

all_noc_codes = read_noc_data()
# Remove weird NOC codes that have duplicate ids
valid_noc_codes = [code for code in all_noc_codes 
                        if code['noc_code'] not in ['11', '1', '0', '14', '12', '13', '10']]

def to_document(code):
    return 'NOC Code ' + code['noc_code'] + '. Job title: ' + code['title'] + '. Description: ' + code['definition']

def to_filename(code):
    return code['id'] + '.json'

data = [{
        'noc': code['noc_code'],
        'title': code['title'], 
        'top_level_code': code['noc_code'][0],
        'teer_code': code['noc_code'][1] if len(code['noc_code']) >= 2 else 'n/a',
        'doc_url': to_document(code),
        } for code in valid_noc_codes]

csv_filename = 'data/noc/data.csv'
fieldnames = ['noc', 'title', 'top_level_code', 'teer_code', 'doc_url']

with open(csv_filename, 'w', newline='') as csv_file:
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(data)
