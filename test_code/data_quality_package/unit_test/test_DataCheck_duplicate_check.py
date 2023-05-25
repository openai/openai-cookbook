import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as f
from pyspark.sql.types import StringType, DateType, IntegerType, FloatType, DoubleType
from test_code.data_quality_package.dq_utility import DataCheck

# Create SparkSession
spark = SparkSession.builder \
    .appName("Data Quality Unit Test") \
    .getOrCreate()

# Create DataFrame
df = spark.read.parquet("data/test_data.parquet")

# DataCheck instance fixture
@pytest.fixture
def datacheck_instance():
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return data_check

# Test duplicate_check function
def test_duplicate_check(datacheck_instance):
    input_col = "Patient Number"
    schema_col = input_col + " schema"
    duplicate_cond = (datacheck_instance.duplicate_cond_syntax(schema_col)) & (
        (f.col(input_col).isNotNull()) | (f.col(input_col) != "")
    )
    duplicate_error_msg = f"unique_FAIL: Column [{input_col}] is not unique.]"
    error_col_name = input_col + " duplicate_check"

    datacheck_instance.duplicate_check(input_col)

    assert error_col_name in datacheck_instance.source_df.columns
    assert error_col_name not in datacheck_instance.source_df.drop(f.col("Duplicate_indicator")).columns
    assert duplicate_error_msg in datacheck_instance.error_columns