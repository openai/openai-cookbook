import json
import math
import pandas as pd
import pytest
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from test_code.data_quality_package.dq_utility import DataCheck

# Create SparkSession
spark = SparkSession.builder \
    .appName("Data Quality Unit Test") \
    .getOrCreate()

# Create DataFrame
data = [
    ("123", "Active", "Sub Status 1", "Plan Type 1", "High", "Payer 1", "2021-01-01", 10, 80, 20, 1000, "2021-01-02", "2021-01-03", "2021-01-04", "2021-01-05", "2021-12-31"),
    ("124", "Inactive", "Sub Status 2", "Plan Type 2", "Low", "Payer 2", "2021-02-01", 20, 70, 30, 2000, "2021-02-02", "2021-02-03", "2021-02-04", "2021-02-05", "2021-12-31"),
    ("125", "Active", "Sub Status 3", "Plan Type 3", "Medium", "Payer 3", "2021-03-01", 30, 60, 40, 3000, "2021-03-02", "2021-03-03", "2021-03-04", "2021-03-05", "2021-12-31"),
]

columns = [
    "Patient Number",
    "Current Patient Status",
    "Current Patient Sub Status",
    "Plan Type",
    "Plan Priority",
    "Payer Name",
    "Final Outcome Date",
    "Days From First Call to Insurer To Final Outcome Date",
    "Coverage %",
    "Co Payment %",
    "Plan Max Amount",
    "Submitted To MD Date",
    "Received From MD Date",
    "Submitted To Insurer Date",
    "Result Date",
    "Expiry Date",
]

df = spark.createDataFrame(data, columns)

@pytest.fixture
def datacheck_instance():
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    return DataCheck(source_df=df, spark_context=spark, config_path=config_path, file_name=file_name, src_system=src_system)

def test_main_pipeline(datacheck_instance):
    error_df, sns_message = datacheck_instance.main_pipeline()
    assert error_df is not None
    assert sns_message == []

def test_null_check(datacheck_instance):
    datacheck_instance.null_check("Patient Number")
    assert "Patient Number null_check" in datacheck_instance.source_df.columns

def test_data_type_check(datacheck_instance):
    datacheck_instance.data_type_check("Patient Number")
    assert "Patient Number type_check" in datacheck_instance.source_df.columns

def test_duplicate_check(datacheck_instance):
    datacheck_instance.duplicate_check("Patient Number")
    assert "Patient Number duplicate_check" in datacheck_instance.source_df.columns

def test_range_check(datacheck_instance):
    datacheck_instance.range_check("Coverage %")
    assert "Coverage % range_check" in datacheck_instance.source_df.columns

def test_category_check(datacheck_instance):
    datacheck_instance.category_check("Current Patient Status")
    assert "Current Patient Status category_check" in datacheck_instance.source_df.columns

def test_conditional_check(datacheck_instance):
    datacheck_instance.conditional_check("Current Patient Sub Status")
    assert "Current Patient Sub Status conditional_check" in datacheck_instance.source_df.columns