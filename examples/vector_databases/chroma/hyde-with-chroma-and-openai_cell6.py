# Load the claim dataset
import pandas as pd

data_path = '../../data'

claim_df = pd.read_json(f'{data_path}/scifact_claims.jsonl', lines=True)
claim_df.head()