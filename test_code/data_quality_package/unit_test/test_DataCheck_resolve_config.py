import ast
import json
import pytest
from pyspark.sql import SparkSession
from unittest.mock import MagicMock
from test_code.data_quality_package.dq_utility import DataCheck

# Create DataFrame
@pytest.fixture
def spark():
    return SparkSession.builder.master("local").appName("DataCheck Test").getOrCreate()

@pytest.fixture
def df(spark):
    return spark.read.parquet("data/test_data.parquet")

@pytest.fixture
def datacheck_instance(spark, df):
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return DataCheck(source_df=df, spark_context=spark, config_path="config.json", file_name="az_ca_pcoe_dq_rules_innomar.csv", src_system="bioscript")

def test_resolve_config(datacheck_instance):
    env_path = "s3://config-path-for-chat-gpt-unit-test/env.json"
    config_content = {
        "subs": {
            "<env>": "test",
            "<_env>": "test",
            "<bucket_name>": "test-bucket",
            "<account>": "test-account"
        }
    }

    datacheck_instance.read_s3_file = MagicMock(return_value=json.dumps(config_content).encode())
    result = datacheck_instance.resolve_config(env_path, config_content)

    expected_result = {
        "subs": {
            "test": "test",
            "test": "test",
            "test-bucket": "test-bucket",
            "test-account": "test-account"
        }
    }

    assert result == expected_result