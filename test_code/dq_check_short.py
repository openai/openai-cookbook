from pyspark.sql.functions import broadcast
from pyspark.sql import SparkSession
from pyspark.sql.types import StringType, IntegerType, DateType, FloatType, DoubleType
import pandas as pd
import ast
import logging
import pyspark.sql.functions as f
import math
import numpy as np
from pyspark.sql.column import Column
from pyspark.sql.dataframe import DataFrame
from pyspark.sql.utils import AnalysisException
import json
import boto3
from botocore.exceptions import ClientError
from pandas.core.indexes.base import Index
from urllib.parse import urlparse
from typing import Union

# Create logger utility
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Define boto3 APIs
s3_client = boto3.client("s3")
s3_client = boto3.client("s3")
s3_resource = boto3.resource("s3")


class DataCheck:
    def __init__(
        self,
        source_df: DataFrame,
        spark_context: SparkSession.builder.getOrCreate,
        config_path: str,
        file_name: str,
        src_system: str,
    ) -> None:
        """
        A class checking the quality of a source data frame based on the given criteria.
        :param source_df (DataFrame): the source data frame to apply the data quality checks on.
        :param spark_context (SparkSession.builder.getOrCreate): the spark session to run the data quality check.
        :param config_path (str): the path to config csv file.
        :param file_name (str): the name of the file to check the data quality check on
        :param src_system (str): the source of the file where it comes from (vendor)
        :raise KeyError: raise a key error if the columns in the source data frame is not in the config file.
        """
        # Set variables
        self.spark = spark_context
        self.source_df = source_df

        self.error_df = None
        self.error_columns = []
        self.error_counter = 0
        self.schema_dict = {
            "StringType": StringType,
            "DateType": DateType,
            "IntegerType": IntegerType,
            "FloatType": FloatType,
            "DoubleType": DoubleType,
        }

        # Initial configuration
        config_content = self.read_s3_file(config_path).decode()
        self.config = self.resolve_config(config_path.replace("config.json", "env.json"), json.loads(config_content))

        dq_rule_path = self.config[src_system]["dq_rule_path"]
        # dq_rule_content = self.read_s3_file(dq_rule_path)
        self.rule_df = pd.read_csv(dq_rule_path, index_col="column_name")
        self.file_name = file_name
        self.rule_df = self.rule_df[(self.rule_df["file_name"] == self.file_name)]
        self.rule_df = self.rule_df.applymap(lambda x: x if x else np.nan)
        self.rule_df.sort_index(inplace=True)
        self.sns_message = []

        self.input_columns = self.source_df.columns
        self.output_columns = self.config[src_system]["sources"][self.file_name]["dq_output_columns"]
        for index in range(len(self.input_columns)):
            if "." in self.input_columns[index]:
                self.input_columns[index] = "`" + self.input_columns[index] + "`"

        missed_columns = set(self.input_columns) - set(self.rule_df.index)
        if len(missed_columns) > 0:
            logger.warning(f"[{missed_columns}] are not found in the rule file.")

        self.spark.conf.set("spark.sql.legacy.timeParserPolicy", "LEGACY")
        # self.spark.conf.set("spark.sql.legacy.timeParserPolicy", "CORRECTED")
        self.spark.conf.set("spark.sql.adaptive.enabled", True)
        self.spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", True)

    def read_s3_file(self, file_path) -> bytes:
        """
        Read s3 file content and return it in byte format
        :param file_path: full s3 object path
        :return byte content of the file
        """
        file_res = urlparse(file_path)
        try:
            file_obj = s3_resource.Object(file_res.netloc, file_res.path.lstrip("/"))
            return file_obj.get()["Body"].read()
        except ClientError:
            raise FileNotFoundError(f"File cannot be found in S3 given path '{file_path}'")

    def resolve_config(self, env_path, config_content):
        """
        Read config content and resolve env variables
        :param env_path: environment file path
        :param config_content: environment agnostic config file
        :return environmentally resolved config
        """
        env_content = self.read_s3_file(env_path).decode()
        env_sub = json.loads(env_content)["subs"]

        config_content_str = (
            str(config_content)
            .replace("<env>", env_sub["<env>"])
            .replace("<_env>", env_sub["<_env>"])
            .replace("<bucket_name>", env_sub["<bucket_name>"])
            .replace("<account>", env_sub["<account>"])
        )

        return ast.literal_eval(config_content_str)

    @staticmethod
    def is_float(element) -> bool:
        """
        Check if the given input can be returned as float or not.
        :param element: The input which can be anything (_type_).
        :return bool: whether it is float (True) or not (False).
        """
        try:
            float(element)
            return True
        except ValueError:
            return False

    def limit_finder(self, input_col: str, rule_value: Union[str, int, float]) -> Union[float, Column, None]:
        """
        Finds the limit based on the given column. If it is a number it returns the number or if it is a column it returns the f.col.
        :param input_col: the column to check this condition on
        :param rule_value: value of the limit no matter the datatype
        :return Union[str, Column, None]: whether a float or a column in order to check for range check.
        :raise KeyError: if the input_col needs other columns that is not in the dataset it will raise an error.
        """
        if self.is_float(rule_value):
            rule_value = float(rule_value)
            if math.isnan(rule_value):
                return None
            else:
                return rule_value
        elif type(rule_value) == str:
            if rule_value not in self.input_columns:
                print(rule_value)
                self.sns_message.append(
                    f"column {rule_value} is not in report {self.file_name} while it is {input_col} needed for range check"
                )
                return None
            return f.col(rule_value)

    def columns_to_check(self, criteria: str) -> Index:
        """
        Returns the indexes to be used while working on the check rules.
        :param criteria: whether it is data type, nullable, etc.
        :return Index: the index of the columns that this condition should be met.
        """
        return self.rule_df[(self.rule_df[criteria]).notna()].index

    def add_error_col(self, error_msg: str, condition: Column, error_col_name: str) -> None:
        """
        Add an error column based on the condition to filter and the error message
        :param error_msg: the error message to be added if the condition is met
        :param condition: the condition of the error to be met in order to return the error column
        :param error_col_name: the name of the error column
        """
        if condition is not None and error_col_name and error_msg:
            col_condition = f.when(condition, f.lit(error_msg)).otherwise(f.lit(None))
            error_col_name = error_col_name + str(self.error_counter)
            self.source_df = self.source_df.withColumn(error_col_name, col_condition)
            self.error_columns.append(f.col(error_col_name))
            self.error_counter += 1

    def data_type_check(self, input_col: str) -> None:
        """
        Checks the data type of all columns and give an error column for each column
        :param input_col: the column to apply this check.
        """
        print("start data type check")
        dtype_key = self.rule_df.loc[input_col, "type"]
        if dtype_key == "DateType":
            date_format = self.rule_df.loc[input_col, "date_format"]
            self.source_df = self.source_df.withColumn(input_col + " schema", f.to_date(f.col(input_col), date_format))
            # self.source_df.select(input_col + ' schema').cache()
        else:
            dtype = self.schema_dict[dtype_key]()
            self.source_df = self.source_df.withColumn(input_col + " schema", f.col(input_col).cast(dtype))
            # self.source_df.select(input_col + ' schema').cache()
        # dtype_cond should check if the given input_col is not null and the one with schema is null.
        dtype_cond = ((f.col(input_col).isNotNull()) | (f.col(input_col) != "")) & (
            f.col(input_col + " schema").isNull()
        )
        type_error_msg = f"data_type_FAIL: Column [{input_col}] should be {dtype_key}"
        self.add_error_col(error_msg=type_error_msg, condition=dtype_cond, error_col_name=input_col + " type_check")
        logger.info(f"[{input_col}] dtype check is done.")

    def null_cond_syntax(self, input_col: str) -> Column:
        """
        The condition for a null check.
        :param input_col: the column to apply the check on.
        :raise Column: The not null condition column.
        """
        return (f.col(input_col) == "") | (f.col(input_col).isNull())

    def null_check(self, input_col: str) -> None:
        """
        Checks not nullable columns and give an error column for input_col
        :param input_col: The column to apply the null check.
        """
        print("start null_check")
        if not math.isnan(self.rule_df.loc[input_col, "nullable"]):
            return
        null_condition = self.null_cond_syntax(input_col)
        null_error_msg = f"null_FAIL: Column [{input_col}] cannot be null"
        self.add_error_col(error_msg=null_error_msg, condition=null_condition, error_col_name=input_col + " null_check")
        logger.info(f"[{input_col}] null check is done.")

    def sum_check_syntax(self, input_col1: str, input_col2: str, syntax_value: float) -> Column:
        """
        The syntax to check for sum of 2 columns to equal a syntax value, to be used in conditional checks.
        :param input_col1: column 1 to check
        :param input_col2: column 2 to check
        :param syntax_value: column value that column 1 and 2 should equal to.
        :return Column: The sum_check Column condition.
        """
        return ~(f.col(input_col1) + f.col(input_col2) != syntax_value)

