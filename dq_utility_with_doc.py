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

    def conditional_cond_syntax(self, input_col: str, condition_column: str, conditional_variables: str) -> Column:
        """
        Generates a Column condition given input column and the condition column.
        :param input_col: The column in which the current syntax is applied on
        :param condition_column: the second column which might be used in this conditional check.
        :param conditional_variables: The variables of the check. It could be __NOT__NULL__, a string of comma separated variables or a single number.
        :return Column: The conditional column condition.
        """
        not_category = []
        if conditional_variables == "__NOT__NULL__":
            category_cond = ~self.null_cond_syntax(input_col)
            conditional_msg = f"{input_col} is not null,"
            return category_cond, conditional_msg
        elif self.is_float(conditional_variables):
            category_cond = self.sum_check_syntax(
                input_col + " schema", condition_column + " schema", conditional_variables
            )
            conditional_msg = f"[{input_col}] and [{condition_column}] sum is not equal to {conditional_variables}"
            return category_cond, conditional_msg
        else:
            category_list = conditional_variables.split(",")
            for ind, value in enumerate(category_list):
                if "__NOT__" == value[: len("__NOT__")]:
                    not_category.append(category_list.pop(ind)[len("__NOT__") :])

            category_cond = f.col(input_col).isin(category_list) == True
            if not_category:
                category_cond = category_cond & (f.col(input_col).isin(not_category) == False)
            conditional_msg = f"[{input_col}] is in category ({category_list}),)"
            return category_cond, conditional_msg

    def conditional_check(self, input_col: str) -> None:
        """
        Checks all the conditional columns in a single row in a config csv file.
        :param input_col: The column to apply the check on.
        """
        multiple_conditional_list = self.rule_df.loc[input_col, "conditional_columns"].split(";")
        for cond_ind, condition_columns in enumerate(multiple_conditional_list):
            current_additional_cond_value = self.rule_df.loc[input_col, "conditional_column_value"].split(";")[cond_ind]
            current_conditional_valuelist = self.rule_df.loc[input_col, "conditional_valuelist"].split(";")[cond_ind]

            first_col_cond, first_col_msg = self.conditional_cond_syntax(
                input_col=input_col,
                condition_column=condition_columns,
                conditional_variables=current_conditional_valuelist,
            )
            for condition_column in condition_columns.split(","):
                if condition_column in self.input_columns:
                    second_cal_cond, second_col_msg = self.conditional_cond_syntax(
                        input_col=condition_column,
                        condition_column=input_col,
                        conditional_variables=current_additional_cond_value,
                    )
                    conditional_cond = first_col_cond & (~second_cal_cond)
                    conditional_error_msg = f"Cond_fail: {first_col_msg}+{second_col_msg}"
                    self.add_error_col(
                        error_msg=conditional_error_msg,
                        condition=conditional_cond,
                        error_col_name=input_col + " conditional_check",
                    )
                else:
                    self.sns_message.append(
                        f"Column {condition_column} is not in report {self.file_name} while it is needed for conditional check"
                    )
        logger.info(f"[{input_col}] conditional check is done.")

    def range_cond_syntax(self, input_col: str) -> Column:
        """
        The range check column condition
        :param input_col: The column to apply the check on
        :return Column: The range check column condition.
        """
        schema_col = input_col + " schema"
        output_cond = None

        min_str = self.rule_df.loc[input_col, "min"]
        min_value = self.limit_finder(input_col, min_str)
        if min_value is not None:
            output_cond = output_cond | (f.col(schema_col) < min_value)
        max_str = self.rule_df.loc[input_col, "max"]
        max_value = self.limit_finder(input_col, max_str)
        if max_value is not None:
            output_cond = output_cond | (f.col(schema_col) > max_value)
        return min_str, max_str, output_cond

    def range_check(self, input_col: str) -> None:
        """
        This method checks input_col with a range check and add an error column to self.source_df.
        Args:
            input_col (str): the column to check.
        """
        print("start range_check")
        min_str, max_str, range_error_cond = self.range_cond_syntax(input_col)
        range_error_cond = range_error_cond & ((f.col(input_col).isNotNull()) | (f.col(input_col) != ""))
        range_error_msg = f"range_FAIL: Column [{input_col}] must be in range ([{min_str}]<{input_col}<[{max_str}])"
        self.add_error_col(
            error_msg=range_error_msg, condition=range_error_cond, error_col_name=input_col + " range_check"
        )
        logger.info(f"[{input_col}] range check is done.")

    def file_check(self, input_col):
        # finding source side columns
        source_df_columns_list = [input_col]
        reference_columns_str = self.rule_df.loc[input_col, "reference_columns"]
        if type(reference_columns_str) == str:
            additional_columns_list = reference_columns_str.replace(", ", ",").replace(" ,", ",").split(",")
            source_df_columns_list.extend(additional_columns_list)

        # Find reference side columns
        file_check_type = self.rule_df.loc[input_col, "reference_valuelist"]
        print("file check type", file_check_type)
        current_file_config = self.config["dq_referential_files"][file_check_type]
        reference_columns = current_file_config["reference_columns"]
        print("ref cols", reference_columns)

        # Read reference file
        file_path = current_file_config["path"]
        file_df = self.spark.read.option("header", "true").csv(file_path)
        # changing columns names on reference to be the same as source
        print("src df cols list", source_df_columns_list)
        for col_ind, ref_col in enumerate(reference_columns):
            source_col = source_df_columns_list[col_ind]
            try:
                file_df = file_df.withColumnRenamed(ref_col, source_col)
                file_df = file_df.withColumn(source_col, f.trim(f.upper(f.col(source_col))))
                file_df = file_df.withColumn(source_col, f.regexp_replace(source_col, "-", " "))
                self.source_df = self.source_df.withColumn(source_col, f.trim(f.upper(f.col(source_col))))
                self.source_df = self.source_df.withColumn(source_col, f.regexp_replace(source_col, "-", " "))
                if "Postal Code".upper() in source_col.upper():
                    self.source_df = self.source_df.withColumn(source_col, f.regexp_replace(source_col, " ", ""))
            except AnalysisException:
                self.sns_message.append(f"Column {ref_col} is not found in the RDW file needed for DQ check")
                return None, None

        pre_join_columns = set(self.source_df.columns)
        self.source_df = self.source_df.join(file_df, source_df_columns_list, how="left")
        post_join_columns = set(self.source_df.columns)
        join_col = tuple(post_join_columns - pre_join_columns)[0]
        file_cond = (f.col(join_col).isNull()) & ((f.col(input_col).isNotNull()) | (f.col(input_col) != ""))
        file_error_msg = (
            f"{file_check_type}_FAIL: Column [{source_df_columns_list}] did not pass the {file_check_type}."
        )
        return file_cond, file_error_msg

    def category_check(self, input_col: str) -> None:
        """
        Method checks input_col with a category and add an error column to self.source_df.
        :param input_col: the column to check.
        """
        print("start category check")
        valuelist_type = self.rule_df.loc[input_col, "reference_valuelist"].upper()
        if valuelist_type[0:2] == "__":
            category_cond, category_error_msg = self.file_check(input_col)
        else:
            category_list = valuelist_type.split(",")
            self.source_df = self.source_df.withColumn(input_col, f.trim(f.upper(f.col(input_col))))
            category_cond = (f.col(input_col).isin(category_list) == False) & (
                (f.col(input_col).isNotNull()) | (f.col(input_col) != "")
            )
            category_error_msg = f"category_FAIL: Column [{input_col}] accepted values are ({category_list}])"
        self.add_error_col(
            error_msg=category_error_msg, condition=category_cond, error_col_name=input_col + " category_check"
        )
        logger.info(f"[{input_col}] category check is done.")

    def duplicate_cond_syntax(self, input_col: str) -> Column:
        """
        The duplicate check column condition
        :param input_col: The column to apply the check on.
        :raise Column: the duplicate check column condition.
        """
        self.source_df = self.source_df.join(
            broadcast(self.source_df.groupBy(input_col).agg((f.count("*")).alias("Duplicate_indicator"))),
            on=input_col,
            how="inner",
        )
        return f.col("Duplicate_indicator") > 1

    def duplicate_check(self, input_col: str) -> None:
        """
        This method checks input_col with should be unique and add an error column to self.source_df.
        :param input_col: the column to check.
        """
        print("start duplicate_check")
        schema_col = input_col + " schema"
        duplicate_cond = (self.duplicate_cond_syntax(schema_col)) & (
            (f.col(input_col).isNotNull()) | (f.col(input_col) != "")
        )
        duplicate_error_msg = f"unique_FAIL: Column [{input_col}] is not unique.])"
        self.add_error_col(
            error_msg=duplicate_error_msg, condition=duplicate_cond, error_col_name=input_col + " duplicate_check"
        )
        self.source_df = self.source_df.drop(f.col("Duplicate_indicator"))
        logger.info(f"[{input_col}] duplicate check is done.")

    def main_pipeline(self) -> DataFrame:
        """
        The main pipeline to do all the checks on the given data frame.
        :return DataFrame: The consolidated error dataframe.
        """

        columns_to_check_dict = {}
        columns_to_check_dict[self.data_type_check] = self.columns_to_check("type")
        columns_to_check_dict[self.null_check] = self.rule_df[(self.rule_df["nullable"]).isna()].index
        columns_to_check_dict[self.duplicate_check] = self.columns_to_check("unique")
        columns_to_check_dict[self.category_check] = self.columns_to_check("reference_valuelist")
        columns_to_check_dict[self.range_check] = list(
            set(self.columns_to_check("min")) | set(self.columns_to_check("max"))
        )

        for index in range(len(self.input_columns)):
            print("inpul col", self.input_columns[index])
            for check_type in columns_to_check_dict.keys():
                if self.input_columns[index] in columns_to_check_dict[check_type]:
                    check_type(self.input_columns[index])

        # conditional column in a different loop since they rely on schema of the multiple columns.
        columns_to_check_dict[self.conditional_check] = self.columns_to_check("conditional_columns")
        for conditional_col in columns_to_check_dict[self.conditional_check]:
            if conditional_col in self.input_columns:
                self.conditional_check(conditional_col)
            else:
                self.sns_message.append(
                    f"column {conditional_col} is not in report {self.file_name} while it is needed for conditional check"
                )

        # combining all error columns to one column.
        self.source_df = (
            self.source_df.withColumn("temp", f.array(self.error_columns))
            .withColumn("final", f.expr("FILTER(temp, x -> x is not null)"))
            .drop("temp")
        )

        # exploding the error column into multiple rows.
        print("exploding error df")
        self.error_df = self.source_df.select(self.output_columns[0], f.explode("final").alias("Error")).filter(
            f.col("Error").isNotNull()
        )

        if self.error_df and self.error_df.rdd.isEmpty():
            self.error_df = None
        return self.error_df, self.sns_message
