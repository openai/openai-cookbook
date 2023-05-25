import math
import pytest
from typing import Any, Tuple, Union
from pyspark.sql import SparkSession
from pyspark.sql.types import StringType, DateType, IntegerType, FloatType, DoubleType
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

def test_range_cond_syntax(datacheck_instance):
    input_col = "Patient Number"
    min_str, max_str, output_cond = datacheck_instance.range_cond_syntax(input_col)

    assert min_str == "null"
    assert max_str == "null"
    assert output_cond is None

    input_col = "Coverage %"
    min_str, max_str, output_cond = datacheck_instance.range_cond_syntax(input_col)

    assert min_str == "0"
    assert max_str == "100"
    assert output_cond is not None