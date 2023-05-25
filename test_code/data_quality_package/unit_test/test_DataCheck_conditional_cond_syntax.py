import json
import numpy as np
import pandas as pd
import pytest
from pyspark.sql import SparkSession
from pyspark.sql.functions import col as f_col
from pyspark.sql.types import StringType, DateType, IntegerType, FloatType, DoubleType
from typing import Any, Tuple, Union
from unittest.mock import MagicMock

from test_code.data_quality_package.dq_utility import DataCheck

# Create DataFrame
@pytest.fixture
def spark():
    spark_session = SparkSession.builder \
        .appName("pytest") \
        .master("local") \
        .getOrCreate()
    return spark_session

@pytest.fixture
def df(spark):
    return spark.read.parquet("data/test_data.parquet")

@pytest.fixture
def datacheck_instance(df, spark):
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    return DataCheck(source_df=df, spark_context=spark, config_path="config.json", file_name="az_ca_pcoe_dq_rules_innomar.csv", src_system="bioscript")

def test_conditional_cond_syntax_not_null(datacheck_instance):
    input_col = "Patient Number"
    condition_column = "Current Patient Status"
    conditional_variables = "__NOT__NULL__"

    category_cond, conditional_msg = datacheck_instance.conditional_cond_syntax(input_col, condition_column, conditional_variables)

    assert category_cond is not None
    assert isinstance(category_cond, f_col)
    assert conditional_msg == f"{input_col} is not null,"

def test_conditional_cond_syntax_float(datacheck_instance):
    input_col = "Coverage %"
    condition_column = "Co Payment %"
    conditional_variables = "0.5"

    category_cond, conditional_msg = datacheck_instance.conditional_cond_syntax(input_col, condition_column, conditional_variables)

    assert category_cond is not None
    assert isinstance(category_cond, f_col)
    assert conditional_msg == f"[{input_col}] and [{condition_column}] sum is not equal to {conditional_variables}"

def test_conditional_cond_syntax_category(datacheck_instance):
    input_col = "Plan Type"
    condition_column = "Plan Priority"
    conditional_variables = "A,B,__NOT__C"

    category_cond, conditional_msg = datacheck_instance.conditional_cond_syntax(input_col, condition_column, conditional_variables)

    assert category_cond is not None
    assert isinstance(category_cond, f_col)
    assert conditional_msg == f"[{input_col}] is in category (['A', 'B']),"