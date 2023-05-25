import boto3
import json
import pandas as pd
import pytest
from botocore.exceptions import ClientError
from pyspark.sql import SparkSession
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

from test_code.data_quality_package.dq_utility import DataCheck

# Create DataFrame
@pytest.fixture
def spark():
    return SparkSession.builder.master("local").appName("DataCheckTest").getOrCreate()

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

def test_read_s3_file(datacheck_instance):
    # Mock S3 resource and object
    with patch("boto3.resource") as mock_resource:
        mock_s3_object = MagicMock()
        mock_resource.return_value.Object.return_value = mock_s3_object
        mock_s3_object.get.return_value = {"Body": MagicMock(read=lambda: b"test content")}

        # Test valid file path
        file_path = "s3://test-bucket/test-key"
        result = datacheck_instance.read_s3_file(file_path)
        assert result == b"test content"

        # Test invalid file path
        mock_s3_object.get.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        with pytest.raises(FileNotFoundError):
            datacheck_instance.read_s3_file("s3://test-bucket/invalid-key")

def test_read_s3_file_invalid_url(datacheck_instance):
    # Test invalid URL
    with pytest.raises(ValueError):
        datacheck_instance.read_s3_file("invalid-url")