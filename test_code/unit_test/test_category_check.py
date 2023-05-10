import json
import pandas as pd
from unittest import TestCase
from pyspark.sql import SparkSession
from pyspark.sql import functions as f
from test_code.dq_utility import DataCheck

class TestDataCheckCategoryCheck(TestCase):
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

    def test_category_check(self):
        input_col = "column_name_to_test"

        initial_error_counter = self.data_check.error_counter
        initial_error_columns = self.data_check.error_columns.copy()

        self.data_check.category_check(input_col)

        # Test if the error_counter is incremented
        self.assertEqual(self.data_check.error_counter, initial_error_counter + 1)

        # Test if the error_columns list is updated
        self.assertNotEqual(self.data_check.error_columns, initial_error_columns)

        # Test if the source_df has the new error column
        error_col_name = input_col + " category_check" + str(initial_error_counter)
        self.assertIn(error_col_name, self.data_check.source_df.columns)

        # Test if the error message appears in the new error column for rows that meet the condition
        error_rows = self.data_check.source_df.filter(f.col(error_col_name).isNotNull()).count()
        self.assertGreater(error_rows, 0)

if __name__ == '__main__':
    import pytest
    pytest.main(['-v', '-k', 'TestDataCheckCategoryCheck'])