import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as f
from pyspark.sql.types import StringType, IntegerType
from test_code.data_quality_package.dq_utility import DataCheck

# Create SparkSession
spark = SparkSession.builder \
    .appName("pytest") \
    .getOrCreate()

# Create DataFrame
data = [
    ("A", "B", 3),
    ("C", "D", 5),
    ("E", "F", 7)
]
schema = ["col1", "col2", "col3"]
df = spark.createDataFrame(data, schema)

# Create DataCheck instance
@pytest.fixture
def datacheck_instance():
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return DataCheck(source_df=df, spark_context=spark, config_path="config.json", file_name="az_ca_pcoe_dq_rules_innomar.csv", src_system="bioscript")

# Test sum_check_syntax
def test_sum_check_syntax(datacheck_instance):
    input_col1 = "col1"
    input_col2 = "col2"
    syntax_value = "AB"
    expected_result = df.withColumn("result", ~(f.col(input_col1) + f.col(input_col2) != syntax_value))

    result = datacheck_instance.sum_check_syntax(input_col1, input_col2, syntax_value)
    assert result == expected_result