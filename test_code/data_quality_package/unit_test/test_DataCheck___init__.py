import json
import pytest
from pyspark.sql import SparkSession
from test_code.data_quality_package.dq_utility import DataCheck
from unittest.mock import MagicMock

# Create DataFrame
@pytest.fixture(scope="module")
def spark():
    spark = SparkSession.builder.master("local").appName("DataCheckTest").getOrCreate()
    return spark

@pytest.fixture(scope="module")
def df(spark):
    return spark.read.parquet("data/test_data.parquet")

@pytest.fixture(scope="module")
def datacheck_instance(spark, df):
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return data_check

def test_datacheck_init(spark, df, datacheck_instance):
    assert datacheck_instance.spark == spark
    assert datacheck_instance.source_df == df
    assert datacheck_instance.error_df is None
    assert datacheck_instance.error_columns == []
    assert datacheck_instance.error_counter == 0
    assert datacheck_instance.schema_dict == {
        "StringType": StringType,
        "DateType": DateType,
        "IntegerType": IntegerType,
        "FloatType": FloatType,
        "DoubleType": DoubleType,
    }
    assert datacheck_instance.s3_client is not None
    assert datacheck_instance.s3_resource is not None
    assert datacheck_instance.config is not None
    assert datacheck_instance.rule_df is not None
    assert datacheck_instance.file_name == "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    assert datacheck_instance.sns_message == []

    missed_columns = set(datacheck_instance.input_columns) - set(datacheck_instance.rule_df.index)
    assert len(missed_columns) == 0

    assert datacheck_instance.output_columns == 'Patient Number'
    assert datacheck_instance.spark.conf.get("spark.sql.legacy.timeParserPolicy") == "LEGACY"
    assert datacheck_instance.spark.conf.get("spark.sql.adaptive.enabled") == "true"
    assert datacheck_instance.spark.conf.get("spark.sql.adaptive.coalescePartitions.enabled") == "true"

def test_read_s3_file(datacheck_instance):
    datacheck_instance.s3_resource.Object = MagicMock()
    datacheck_instance.s3_resource.Object.return_value.get.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"test_content"))}
    file_path = "s3://test-bucket/test-file.txt"
    result = datacheck_instance.read_s3_file(file_path)
    assert result == b"test_content"

def test_resolve_config(datacheck_instance):
    env_path = "s3://config-path-for-chat-gpt-unit-test/env.json"
    config_content = {
        "subs": {
            "<env>": "test_env",
            "<_env>": "test_env",
            "<bucket_name>": "test_bucket",
            "<account>": "test_account",
        }
    }
    result = datacheck_instance.resolve_config(env_path, config_content)
    assert result == {
        "subs": {
            "test_env": "test_env",
            "test_env": "test_env",
            "test_bucket": "test_bucket",
            "test_account": "test_account",
        }
    }