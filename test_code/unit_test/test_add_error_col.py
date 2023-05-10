import json
import pandas as pd
from unittest import TestCase
from pyspark.sql import SparkSession
from pyspark.sql import functions as f
from pyspark.sql import Column
from test_code.dq_utility import DataCheck

class TestDataCheckAddErrorCol(TestCase):
    def setUp(self):
        self.spark = SparkSession.builder.getOrCreate()
        self.source_df = self.spark.read.parquet('test_data.parquet')
        self.config_path = 's3://config-path-for-chat-gpt-unit-test/config.json'
        self.file_name = 'az_ca_pcoe_dq_rules_innomar.csv'
        self.src_system = 'bioscript'

        self.data_check = DataCheck(
            source_df=self.source_df,
            spark_context=self.spark,
            config_path=self.config_path,
            file_name=self.file_name,
            src_system=self.src_system
        )

    def test_add_error_col(self):
        error_msg = "Test error message"
        condition = f.col("column_name") == "test_value"
        error_col_name = "error_col_"

        initial_error_counter = self.data_check.error_counter

        self.data_check.add_error_col(error_msg, condition, error_col_name)

        # Test if the error_counter is incremented
        self.assertEqual(self.data_check.error_counter, initial_error_counter + 1)

        # Test if the error_columns list is updated
        self.assertIn(f.col(error_col_name + str(initial_error_counter)), self.data_check.error_columns)

        # Test if the source_df has the new error column
        self.assertIn(error_col_name + str(initial_error_counter), self.data_check.source_df.columns)

        # Test if the error message appears in the new error column for rows that meet the condition
        error_rows = self.data_check.source_df.filter(f.col(error_col_name + str(initial_error_counter)) == error_msg).count()
        self.assertGreater(error_rows, 0)

if __name__ == '__main__':
    import pytest
    pytest.main(['-v', '-k', 'TestDataCheckAddErrorCol'])