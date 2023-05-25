import pytest
from typing import Any
from test_code.data_quality_package.dq_utility import DataCheck
from pyspark.sql import SparkSession

# Create DataFrame
@pytest.fixture
def datacheck_instance():
    spark = SparkSession.builder.master("local").appName("DataCheckTest").getOrCreate()
    df = spark.read.parquet("data/test_data.parquet")
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return DataCheck(source_df=df, spark_context=spark, config_path="config.json", file_name="az_ca_pcoe_dq_rules_innomar.csv", src_system="bioscript")

def test_is_float(datacheck_instance):
    assert datacheck_instance.is_float("3.14") == True
    assert datacheck_instance.is_float("3") == True
    assert datacheck_instance.is_float("hello") == False
    assert datacheck_instance.is_float(None) == False
    assert datacheck_instance.is_float("") == False
    assert datacheck_instance.is_float("1.23e-4") == True