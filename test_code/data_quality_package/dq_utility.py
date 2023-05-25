import ast
import json
import logging
import math
from typing import Any, List, Optional
from urllib.parse import urlparse

import boto3
import numpy as np
import pandas as pd
import pyspark.sql.dataframe as DataFrame
import pyspark.sql.functions as f
from botocore.exceptions import ClientError
from pandas import DataFrame
from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as f
from pyspark.sql.dataframe import DataFrame
from pyspark.sql.functions import broadcast, col, lit, when
from pyspark.sql.types import (DateType, DoubleType, FloatType, IntegerType,
                               StringType)
from pyspark.sql.utils import AnalysisException

# Create logger utility
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Define boto3 APIs
class DataCheck:
    def __init__(
        self,
        source_df: DataFrame,
        spark_context: SparkSession,
        config_path: str,
        file_name: str,
        src_system: str,
    ) -> None:
        """
        Initializes the DataCheck class.

        Args:
            source_df (DataFrame): The source DataFrame to be checked.
            spark_context (SparkSession): The SparkSession object.
            config_path (str): The path to the configuration file.
            file_name (str): The name of the file to be checked.
            src_system (str): The source system identifier.

        Attributes:
            spark (SparkSession): The SparkSession object.
            source_df (DataFrame): The source DataFrame to be checked.
            error_df (DataFrame): The DataFrame containing errors.
            error_columns (List[str]): The list of error columns.
            error_counter (int): The error counter.
            schema_dict (Dict[str, type]): The dictionary of schema types.
            s3_client (boto3.client): The S3 client object.
            s3_resource (boto3.resource): The S3 resource object.
            config (Dict): The configuration dictionary.
            rule_df (pd.DataFrame): The DataFrame containing data quality rules.
            file_name (str): The name of the file to be checked.
            input_columns (List[str]): The list of input columns.
            output_columns (str): The output columns.
            sns_message (List[str]): The list of SNS messages.
        """
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
        self.s3_client = boto3.client("s3")
        self.s3_resource = boto3.resource("s3")

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
        try:
            self.output_columns = self.config[src_system]["sources"][self.file_name]["dq_output_columns"]
        except:
            self.output_columns= 'Patient Number'
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

    def read_s3_file(self, file_path):
        file_res = urlparse(file_path)
        try:
            file_obj = self.s3_resource.Object(file_res.netloc, file_res.path.lstrip("/"))
            return file_obj.get()["Body"].read()
        except ClientError:
            raise FileNotFoundError(f"File cannot be found in S3 given path '{file_path}'")

    def resolve_config(self, env_path, config_content):
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
    def is_float(element: Any):
        try:
            float(element)
            return True
        except ValueError:
            return False

    def limit_finder(self, input_col, rule_value):
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

    def columns_to_check(self, criteria: str) -> List[Any]:
        """
        Returns a list of column indices that meet the given criteria.

        Args:
            criteria (str): The criteria to filter the columns.

        Returns:
            List[Any]: A list of column indices that meet the given criteria.
        """
        return self.rule_df[(self.rule_df[criteria]).notna()].index

    # ... other methods and attributes ...

    def add_error_col(self, error_msg: str, condition: Optional[Column], error_col_name: str) -> None:
        """
        Adds an error column to the source DataFrame if the given condition is met.

        Args:
            error_msg (str): The error message to be added to the error column.
            condition (pyspark.sql.Column, optional): The condition to be checked. If None, no error column will be added.
            error_col_name (str): The name of the error column.

        Returns:
            None
        """
        if condition is not None and error_col_name and error_msg:
            col_condition = when(condition, lit(error_msg)).otherwise(lit(None))
            error_col_name = error_col_name + str(self.error_counter)
            self.source_df = self.source_df.withColumn(error_col_name, col_condition)
            self.error_columns.append(col(error_col_name))
            self.error_counter += 1
        return None

    def data_type_check(self, input_col):
        print("start data type check")
        dtype_key = self.rule_df.loc[input_col, "type"]
        if dtype_key == "DateType":
            date_format = self.rule_df.loc[input_col, "date_format"]
            self.source_df = self.source_df.withColumn(input_col + " schema", f.to_date(f.col(input_col), date_format))
        else:
            dtype = self.schema_dict[dtype_key]()
            self.source_df = self.source_df.withColumn(input_col + " schema", f.col(input_col).cast(dtype))
        dtype_cond = ((f.col(input_col).isNotNull()) | (f.col(input_col) != "")) & (
            f.col(input_col + " schema").isNull()
        )
        type_error_msg = f"data_type_FAIL: Column [{input_col}] should be {dtype_key}"
        self.add_error_col(error_msg=type_error_msg, condition=dtype_cond, error_col_name=input_col + " type_check")
        logger.info(f"[{input_col}] dtype check is done.")
    # ...
    def null_cond_syntax(self, input_col):
        return (f.col(input_col) == "") | (f.col(input_col).isNull())

    # ...
    def null_check(self, input_col):
        print("start null_check")
        if not math.isnan(self.rule_df.loc[input_col, "nullable"]):
            return
        null_condition = self.null_cond_syntax(input_col)
        null_error_msg = f"null_FAIL: Column [{input_col}] cannot be null"
        self.add_error_col(error_msg=null_error_msg, condition=null_condition, error_col_name=input_col + " null_check")
        logger.info(f"[{input_col}] null check is done.")

    def sum_check_syntax(self, input_col1, input_col2, syntax_value):
        return ~(f.col(input_col1) + f.col(input_col2) != syntax_value)

    def conditional_cond_syntax(self, input_col, condition_column, conditional_variables):
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

    # ... other methods and attributes ...

    # Other methods and attributes here

    def conditional_check(self, input_col: str) -> None:
        """
        Performs a conditional check on the input column based on the rules defined in the rule_df DataFrame.

        Args:
            input_col (str): The name of the input column to perform the conditional check on.

        Returns:
            None

        Raises:
            None

        Notes:
            This method updates the instance attributes such as error columns and sns_message.
            It also logs the completion of the conditional check for the input column.
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

    def range_cond_syntax(self, input_col):
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

    # Other methods and attributes of the class

    def range_check(self, input_col):
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

    # ... other methods and attributes ...

    def category_check(self, input_col: str) -> None:
        """
        Checks if the values in the input column match the categories specified in the rule DataFrame.

        Args:
            input_col (str): The name of the input column to check.

        Returns:
            None

        Raises:
            None

        Examples:
            >>> data_check = DataCheck(source_df, rule_df)
            >>> data_check.category_check("column_name")
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

    def duplicate_cond_syntax(self, input_col):
        self.source_df: DataFrame = self.source_df.join(
            broadcast(self.source_df.groupBy(input_col).agg((f.count("*")).alias("Duplicate_indicator"))),
            on=input_col,
            how="inner",
        )
        return f.col("Duplicate_indicator") > 1

    def duplicate_check(self, input_col):
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

    def main_pipeline(self):

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