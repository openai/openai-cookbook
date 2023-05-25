import pytest
from pyspark.sql import SparkSession
from test_code.data_quality_package.dq_utility import DataCheck
from pyspark.sql.functions import col
import pandas as pd

# Create SparkSession
spark = SparkSession.builder.master("local").appName("DataCheckTest").getOrCreate()

# Create DataFrame
data = [("A",), ("B",), ("C",), ("D",), ("E",)]
schema = ["input_col"]
df = spark.createDataFrame(data, schema)

# Create DataCheck instance
@pytest.fixture
def datacheck_instance():
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"
    rule_df = pd.DataFrame(
        {
            "file_name": ["FSN001 - Fasenra (AstraZeneca) Detailed Reports"],
            "reference_valuelist": ["A,B,C"],
        },
        index=["input_col"],
    )
    data_check = DataCheck(df, spark, config_path, file_name, src_system)
    data_check.rule_df = rule_df
    return data_check

# Test category_check function
def test_category_check(datacheck_instance):
    datacheck_instance.category_check("input_col")
    result_df = datacheck_instance.source_df
    expected_error_msg = "category_FAIL: Column [input_col] accepted values are (['A', 'B', 'C'])"
    assert result_df.filter(col("input_col category_check0").isNotNull()).count() == 2
    assert result_df.filter(col("input_col category_check0") == expected_error_msg).count() == 2