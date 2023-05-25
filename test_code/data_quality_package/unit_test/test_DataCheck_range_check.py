import pytest
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from test_code.data_quality_package.dq_utility import DataCheck

# Create SparkSession
spark = SparkSession.builder \
    .appName("Data Quality Unit Test") \
    .getOrCreate()

# Create DataFrame

df = spark.read.parquet("data/test_data.parquet")

@pytest.fixture
def datacheck_instance():
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return data_check

def test_range_check(datacheck_instance):
    datacheck_instance.range_check("Coverage %")
    error_col_name = "Coverage % range_check0"
    assert error_col_name in datacheck_instance.source_df.columns
    error_count = datacheck_instance.source_df.filter(col(error_col_name).isNotNull()).count()
    assert error_count == 0

def test_range_check_with_error(datacheck_instance):
    datacheck_instance.range_check("Days From First Call to Insurer To Final Outcome Date")
    error_col_name = "Days From First Call to Insurer To Final Outcome Date range_check0"
    assert error_col_name in datacheck_instance.source_df.columns
    error_count = datacheck_instance.source_df.filter(col(error_col_name).isNotNull()).count()
    assert error_count == 1