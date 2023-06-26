import os
import wget
import zipfile
import numpy as np
import pandas as pd
from ast import literal_eval


def download_wikipedia_data(
    data_path: str = '../../data/',
    download_path: str = "./",
    file_name: str = "vector_database_wikipedia_articles_embedded") -> pd.DataFrame:

    data_url = 'https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip'

    csv_file_path = os.path.join(data_path, file_name + ".csv")
    zip_file_path = os.path.join(download_path, file_name + ".zip")
    if os.path.isfile(csv_file_path):
        print("File Downloaded")
    else:
        if os.path.isfile(zip_file_path):
            print("Zip downloaded but not unzipped, unzipping now...")
        else:
            print("File not found, downloading now...")
            # Download the data
            wget.download(data_url, out=download_path)

        # Unzip the data
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(data_path)

        # Remove the zip file
        os.remove('vector_database_wikipedia_articles_embedded.zip')
        print(f"File downloaded to {data_path}")


def read_wikipedia_data(data_path: str = '../../data/', file_name: str = "vector_database_wikipedia_articles_embedded") -> pd.DataFrame:

    csv_file_path = os.path.join(data_path, file_name + ".csv")
    data = pd.read_csv(csv_file_path)
    # Read vectors from strings back into a list
    data['title_vector'] = data.title_vector.apply(literal_eval)
    data['content_vector'] = data.content_vector.apply(literal_eval)
    # Set vector_id to be a string
    data['vector_id'] = data['vector_id'].apply(str)
    return data
