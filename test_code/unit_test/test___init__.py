import json
import pandas as pd
from unittest import TestCase
from pyspark.sql import SparkSession
from test_code.dq_utility import DataCheck

class TestDataCheckInit(TestCase):
    def setUp(self):
        self.spark = SparkSession.builder.getOrCreate()
        self.source_df = self.spark.read.parquet('test_data.parquet')
        self.config_path = 's3://config-path-for-chat-gpt-unit-test/config.json'
        self.file_name = 'az_ca_pcoe_dq_rules_innomar.csv'
        self.src_system = 'bioscript'

    def test_init(self):
        data_check = DataCheck(
            source_df=self.source_df,
            spark_context=self.spark,
            config_path=self.config_path,
            file_name=self.file_name,
            src_system=self.src_system
        )

        # Test if the instance variables are set correctly
        self.assertEqual(self.spark, data_check.spark)
        self.assertEqual(self.source_df, data_check.source_df)
        self.assertEqual(self.file_name, data_check.file_name)

        # Test if the rule_df is a pandas DataFrame and has the correct index
        self.assertIsInstance(data_check.rule_df, pd.DataFrame)
        self.assertEqual(data_check.rule_df.index.name, "column_name")

        # Test if the config is a dictionary and contains the src_system key
        self.assertIsInstance(data_check.config, dict)
        self.assertIn(self.src_system, data_check.config)

        # Test if the input_columns and output_columns are lists
        self.assertIsInstance(data_check.input_columns, list)
        self.assertIsInstance(data_check.output_columns, list)

        # Test if the spark configurations are set correctly
        self.assertEqual(self.spark.conf.get("spark.sql.legacy.timeParserPolicy"), "LEGACY")
        self.assertEqual(self.spark.conf.get("spark.sql.adaptive.enabled"), True)
        self.assertEqual(self.spark.conf.get("spark.sql.adaptive.coalescePartitions.enabled"), True)

if __name__ == '__main__':
    import pytest
    pytest.main(['-v', '-k', 'TestDataCheckInit'])