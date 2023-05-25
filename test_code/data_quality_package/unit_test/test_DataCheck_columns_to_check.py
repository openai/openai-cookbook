import pytest
import pandas as pd
from typing import Any, List
from pyspark.sql import SparkSession
from test_code.data_quality_package.dq_utility import DataCheck

# Create DataFrame
@pytest.fixture
def datacheck_instance():
    spark = SparkSession.builder.master("local").appName("DataCheckTest").getOrCreate()
    df = spark.read.parquet("data/test_data.parquet")
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return data_check

def test_columns_to_check(datacheck_instance):
    # Test case 1: Check for non-null values in the "nullable" column
    criteria = "nullable"
    expected_result = ["Patient Number", "Current Patient Status", "Current Patient Sub Status", "Plan Type", "Plan Priority", "Payer Name", "Final Outcome Date", "Days From First Call to Insurer To Final Outcome Date", "Coverage %", "Co Payment %", "Plan Max Amount", "Submitted To MD Date", "Received From MD Date", "Submitted To Insurer Date", "Result Date", "Expiry Date"]
    result = datacheck_instance.columns_to_check(criteria)
    assert result == expected_result, f"Expected {expected_result} but got {result}"

    # Test case 2: Check for non-null values in the "type" column
    criteria = "type"
    expected_result = ["Patient Number", "Current Patient Status", "Current Patient Sub Status", "Plan Type", "Plan Priority", "Payer Name", "Final Outcome Date", "Days From First Call to Insurer To Final Outcome Date", "Coverage %", "Co Payment %", "Plan Max Amount", "Submitted To MD Date", "Received From MD Date", "Submitted To Insurer Date", "Result Date", "Expiry Date"]
    result = datacheck_instance.columns_to_check(criteria)
    assert result == expected_result, f"Expected {expected_result} but got {result}"

    # Test case 3: Check for non-null values in a non-existing column
    criteria = "non_existing_column"
    expected_result = []
    result = datacheck_instance.columns_to_check(criteria)
    assert result == expected_result, f"Expected {expected_result} but got {result}"