import math
import json
import boto3
import pandas as pd
import numpy as np
import pytest
from pyspark.sql import SparkSession
from pyspark.sql.types import StringType, DateType, IntegerType, FloatType, DoubleType
from pyspark.sql import functions as f
from pyspark.sql.column import Column
from test_code.data_quality_package.dq_utility import DataCheck

# Create DataFrame
@pytest.fixture
def datacheck_instance():
    spark = SparkSession.builder.master("local").appName("DataCheckTest").getOrCreate()
    df = spark.read.parquet("data/test_data.parquet")
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return data_check

def test_null_check(datacheck_instance):
    datacheck_instance.null_check("Patient Number")
    assert "Patient Number null_check0" in datacheck_instance.source_df.columns
    assert datacheck_instance.error_counter == 1
    assert len(datacheck_instance.error_columns) == 1

    datacheck_instance.null_check("Current Patient Status")
    assert "Current Patient Status null_check1" in datacheck_instance.source_df.columns
    assert datacheck_instance.error_counter == 2
    assert len(datacheck_instance.error_columns) == 2

    datacheck_instance.null_check("Plan Type")
    assert "Plan Type null_check2" in datacheck_instance.source_df.columns
    assert datacheck_instance.error_counter == 3
    assert len(datacheck_instance.error_columns) == 3