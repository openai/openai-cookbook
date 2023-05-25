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
    spark = SparkSession.builder.master("local").appName("DataCheckTest").getOrCreate()
    return spark

@pytest.fixture
def df(spark):
    return spark.read.parquet("data/test_data.parquet")

@pytest.fixture
def datacheck_instance(df, spark):
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return data_check

def test_data_type_check(datacheck_instance):
    input_col = "Patient Number"
    datacheck_instance.data_type_check(input_col)
    assert input_col + " schema" in datacheck_instance.source_df.columns
    assert input_col + " type_check0" in datacheck_instance.source_df.columns

    input_col = "Final Outcome Date"
    datacheck_instance.data_type_check(input_col)
    assert input_col + " schema" in datacheck_instance.source_df.columns
    assert input_col + " type_check1" in datacheck_instance.source_df.columns

    input_col = "Coverage %"
    datacheck_instance.data_type_check(input_col)
    assert input_col + " schema" in datacheck_instance.source_df.columns
    assert input_col + " type_check2" in datacheck_instance.source_df.columns

    input_col = "Co Payment %"
    datacheck_instance.data_type_check(input_col)
    assert input_col + " schema" in datacheck_instance.source_df.columns
    assert input_col + " type_check3" in datacheck_instance.source_df.columns

    input_col = "Plan Max Amount"
    datacheck_instance.data_type_check(input_col)
    assert input_col + " schema" in datacheck_instance.source_df.columns
    assert input_col + " type_check4" in datacheck_instance.source_df.columns

    input_col = "Submitted To MD Date"
    datacheck_instance.data_type_check(input_col)
    assert input_col + " schema" in datacheck_instance.source_df.columns
    assert input_col + " type_check5" in datacheck_instance.source_df.columns

    input_col = "Received From MD Date"
    datacheck_instance.data_type_check(input_col)
    assert input_col + " schema" in datacheck_instance.source_df.columns
    assert input_col + " type_check6" in datacheck_instance.source_df.columns

    input_col = "Submitted To Insurer Date"
    datacheck_instance.data_type_check(input_col)
    assert input_col + " schema" in datacheck_instance.source_df.columns
    assert input_col + " type_check7" in datacheck_instance.source_df.columns

    input_col = "Result Date"
    datacheck_instance.data_type_check(input_col)
    assert input_col + " schema" in datacheck_instance.source_df.columns
    assert input_col + " type_check8" in datacheck_instance.source_df.columns

    input_col = "Expiry Date"
    datacheck_instance.data_type_check(input_col)
    assert input_col + " schema" in datacheck_instance.source_df.columns
    assert input_col + " type_check9" in datacheck_instance.source_df.columns