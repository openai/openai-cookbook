import json
import numpy as np
import pandas as pd
import pytest
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from pyspark.sql.types import StringType, DateType, IntegerType, FloatType, DoubleType
from test_code.data_quality_package.dq_utility import DataCheck

# Create DataFrame
@pytest.fixture
def spark():
    spark = SparkSession.builder \
        .appName("pytest") \
        .getOrCreate()
    return spark

@pytest.fixture
def df(spark):
    data = [
        ("123", "Active", "Sub Status 1", "Type 1", "Priority 1", "Payer 1", "2021-01-01", 10, 90.0, 10.0, 1000.0, "2021-01-02", "2021-01-03", "2021-01-04", "2021-01-05", "2021-12-31"),
        ("124", "Inactive", "Sub Status 2", "Type 2", "Priority 2", "Payer 2", "2021-02-01", 20, 80.0, 20.0, 2000.0, "2021-02-02", "2021-02-03", "2021-02-04", "2021-02-05", "2021-12-31"),
    ]
    schema = [
        "Patient Number", "Current Patient Status", "Current Patient Sub Status", "Plan Type", "Plan Priority", "Payer Name", "Final Outcome Date", "Days From First Call to Insurer To Final Outcome Date", "Coverage %", "Co Payment %", "Plan Max Amount", "Submitted To MD Date", "Received From MD Date", "Submitted To Insurer Date", "Result Date", "Expiry Date"
    ]
    return spark.createDataFrame(data, schema)

@pytest.fixture
def datacheck_instance(df, spark):
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    return DataCheck(df, spark, config_path, file_name, src_system)

def test_add_error_col(datacheck_instance):
    datacheck_instance.add_error_col("Test error", col("Patient Number") == "123", "error_col_")
    assert "error_col_0" in datacheck_instance.source_df.columns
    assert datacheck_instance.error_counter == 1
    assert len(datacheck_instance.error_columns) == 1

    datacheck_instance.add_error_col("Test error 2", col("Current Patient Status") == "Inactive", "error_col_")
    assert "error_col_1" in datacheck_instance.source_df.columns
    assert datacheck_instance.error_counter == 2
    assert len(datacheck_instance.error_columns) == 2

    result_df = datacheck_instance.source_df.toPandas()
    assert result_df.loc[result_df["Patient Number"] == "123", "error_col_0"].values[0] == "Test error"
    assert pd.isnull(result_df.loc[result_df["Patient Number"] == "124", "error_col_0"].values[0])
    assert pd.isnull(result_df.loc[result_df["Current Patient Status"] == "Active", "error_col_1"].values[0])
    assert result_df.loc[result_df["Current Patient Status"] == "Inactive", "error_col_1"].values[0] == "Test error 2"