import csv
import json
import random

def generate_random_values(n):
    return [random.uniform(-1, 1) for _ in range(n)]

# longest title is 141, round up to 256
# longest definition is 1658, round up to 2048

key = 0
def next_key():
    global key
    key += 1
    return key


def read_noc_data():
    filename = 'data/NOC-2021-v1.0/NOCs without TEER.csv'
    with open(filename) as noc_file:
        return [
            {
                'primary_key': next_key(), 
                'noc_code': int(row['Code - NOC 2021 V1.0 as number']),
                'title': row['Class title'],
                'definition': row['Class definition'],
                'vector': generate_random_values(128)
            } for row in csv.DictReader(noc_file)
        ]

noc_codes = read_noc_data()

valid_noc_codes = [code for code in noc_codes 
                        if code['noc_code'] not in [11, 1, 0, 14, 12, 13, 10]]

with open('noc_data.json', 'w') as json_file:
    json.dump(valid_noc_codes, json_file, indent=4)

l = max(len(code['title']) for code in noc_codes)
print("Length of the longest title:", l)

l = max(len(code['definition']) for code in noc_codes)
print("Length of the longest definition:", l)
