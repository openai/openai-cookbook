import json
import pandas as pd
import pytest
from pyspark.sql import SparkSession
from pyspark.sql.types import StringType, IntegerType, DateType, FloatType, DoubleType
from pyspark.sql.functions import col
from test_code.data_quality_package.dq_utility import DataCheck

# Create SparkSession
spark = SparkSession.builder.master("local").appName("DataCheckTest").getOrCreate()

# Create DataFrame
@pytest.fixture
def df():
    data = [
        ("123", "Active", "Sub Status 1", "Plan A", "High", "Payer 1", "2021-01-01", 10, 80, 20, 1000, "2021-01-02", "2021-01-03", "2021-01-04", "2021-01-05", "2021-12-31"),
        ("456", "Inactive", "Sub Status 2", "Plan B", "Low", "Payer 2", "2021-02-01", 20, 70, 30, 2000, "2021-02-02", "2021-02-03", "2021-02-04", "2021-02-05", "2021-12-31"),
    ]
    schema = [
        "Patient Number",
        "Current Patient Status",
        "Current Patient Sub Status",
        "Plan Type",
        "Plan Priority",
        "Payer Name",
        "Final Outcome Date",
        "Days From First Call to Insurer To Final Outcome Date",
        "Coverage %",
        "Co Payment %",
        "Plan Max Amount",
        "Submitted To MD Date",
        "Received From MD Date",
        "Submitted To Insurer Date",
        "Result Date",
        "Expiry Date",
    ]
    return spark.createDataFrame(data, schema)

@pytest.fixture
def datacheck_instance(df):
    config = {
        "dq_referential_files": {
            "file_check_type_1": {
                "path": "s3://path-to-file-check-type-1.csv",
                "reference_columns": ["Patient Number", "Plan Type"],
            }
        },
        "innomar": {
            "dq_rule_path": "s3://path-to-dq-rule-file.csv",
            "sources": {
                "FSN001 - Fasenra (AstraZeneca) Detailed Reports": {
                    "dq_output_columns": "Patient Number"
                }
            },
        },
    }
    config_path = "s3://config-path-for-chat-gpt-unit-test/config.json"
    file_name = "FSN001 - Fasenra (AstraZeneca) Detailed Reports"
    src_system = "innomar"

    with open("config.json", "w") as f:
        json.dump(config, f)

    rule_df = pd.DataFrame(
        [
            ("fasenra_astrazeneca_detailed_reports_payer_report_reimb_history", "Patient Number", "FALSE", "StringType", "null", "FALSE", "null", "null", "null", "null", "null", "null", "null", "null", "null"),
        ],
        columns=[
            "file_name",
            "column_name",
            "nullable",
            "type",
            "date_format",
            "unique",
            "min",
            "max",
            "reference_valuelist",
            "reference_columns",
            "conditional_valuelist",
            "conditional_columns",
            "conditional_column_value",
        ],
    )
    rule_df.to_csv("s3://path-to-dq-rule-file.csv", index=False)

    return DataCheck(source_df=df, spark_context=spark, config_path="config.json", file_name=file_name, src_system=src_system)

def test_file_check(df, datacheck_instance):
    input_col = "Patient Number"
    file_check_cond, file_error_msg = datacheck_instance.file_check(input_col)

    assert file_check_cond is not None
    assert isinstance(file_check_cond, col)
    assert file_error_msg == "file_check_type_1_FAIL: Column [['Patient Number']] did not pass the file_check_type_1."