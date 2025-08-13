import os
import csv
import subprocess
import time
from datetime import datetime
import sys

if len(sys.argv) > 2:
    START_DATE = sys.argv[1]
    END_DATE = sys.argv[2]
else:
    START_DATE = '2025-05-01'
    END_DATE = '2025-05-31'

INPUT_CSV = f'hubspot_deals_{START_DATE}_to_{END_DATE}_with_company.csv'
OUTPUT_DIR = 'mixpanel_stats_outputs'
WAIT_SECONDS = 60

os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_company_id(row):
    return row.get('id_empresa', '').strip()

company_ids = set()
with open(INPUT_CSV, newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        company_id = get_company_id(row)
        if company_id:
            company_ids.add(company_id)

print(f"Found {len(company_ids)} unique companies with deals closed in the given range.")

def run_and_check(company_id, output_file):
    while True:
        print(f"  Querying Mixpanel for company_id: {company_id}...")
        process = subprocess.Popen([
            'python', 'src/get_company_stats_simple.py',
            company_id, START_DATE, END_DATE
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output_lines = []
        with open(output_file, 'w') as outfile:
            if process.stdout is not None:
                for line in process.stdout:
                    print(line, end='')  # Print to terminal in real time
                    outfile.write(line)
                    output_lines.append(line)
        process.wait()
        output_str = ''.join(output_lines).lower()
        if ('rate limit' in output_str or '429' in output_str or 'query rate limit exceeded' in output_str):
            print(f"  Rate limit hit for company_id {company_id}. Waiting {WAIT_SECONDS} seconds before retrying...")
            time.sleep(WAIT_SECONDS)
        else:
            break

for idx, company_id in enumerate(company_ids, 1):
    print(f"[{idx}/{len(company_ids)}] Processing company_id: {company_id}")
    output_file = os.path.join(OUTPUT_DIR, f"company_{company_id}_events.csv")
    run_and_check(company_id, output_file)

print("All Mixpanel stats exports complete.") 