import json
import pandas as pd
import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as f
from pyspark.sql.types import StringType, DateType, IntegerType, FloatType, DoubleType
from test_code.data_quality_package.dq_utility import DataCheck

# Create SparkSession
spark = SparkSession.builder.master("local").appName("DataCheckTest").getOrCreate()

# Create DataFrame
df = spark.read.parquet("data/test_data.parquet")

# Create DataCheck instance
@pytest.fixture
def datacheck_instance():
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return data_check

# Test conditional_check function
def test_conditional_check(datacheck_instance):
    input_col = "Patient Number"
    datacheck_instance.conditional_check(input_col)

    # Check if the error column is added to the source DataFrame
    assert f"{input_col} conditional_check0" in datacheck_instance.source_df.columns

    # Check if the error column is added to the error_columns list
    assert f.col(f"{input_col} conditional_check0") in datacheck_instance.error_columns

    # Check if the error counter is incremented
    assert datacheck_instance.error_counter == 1

    # Check if the error message is added to the sns_message list
    condition_column = "Current Patient Status"
    expected_error_msg = f"Column {condition_column} is not in report {datacheck_instance.file_name} while it is needed for conditional check"
    assert expected_error_msg in datacheck_instance.sns_message