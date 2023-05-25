import math
import pytest
from typing import Any, Union
from pyspark.sql import SparkSession
from pyspark.sql.types import StringType, DateType, IntegerType, FloatType, DoubleType
from pyspark.sql import functions as f
from test_code.data_quality_package.dq_utility import DataCheck

# Create DataFrame
@pytest.fixture
def datacheck_instance():
    spark = SparkSession.builder.master("local").appName("unit_test").getOrCreate()
    df = spark.read.parquet("data/test_data.parquet")
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return data_check

def test_limit_finder_float(datacheck_instance):
    input_col = "Coverage %"
    rule_value = "50.0"
    result = datacheck_instance.limit_finder(input_col, rule_value)
    assert result == 50.0

def test_limit_finder_nan(datacheck_instance):
    input_col = "Coverage %"
    rule_value = "nan"
    result = datacheck_instance.limit_finder(input_col, rule_value)
    assert result is None

def test_limit_finder_str_existing_column(datacheck_instance):
    input_col = "Coverage %"
    rule_value = "Patient Number"
    result = datacheck_instance.limit_finder(input_col, rule_value)
    assert isinstance(result, f.Column)

def test_limit_finder_str_not_existing_column(datacheck_instance):
    input_col = "Coverage %"
    rule_value = "NonExistingColumn"
    result = datacheck_instance.limit_finder(input_col, rule_value)
    assert result is None