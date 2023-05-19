import ast
import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import boto3
import numpy as np
import pandas as pd
import pyspark.sql.column as Column
import pyspark.sql.dataframe as DataFrame
import pyspark.sql.functions as f
from boto3.resources.base import ServiceResource
from botocore.exceptions import ClientError
from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as f
from pyspark.sql.column import Column
from pyspark.sql.dataframe import DataFrame
from pyspark.sql.functions import broadcast
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
        Initializes the class with the given parameters.

        Args:
            source_df (DataFrame): The source DataFrame.
            spark_context (SparkSession): The SparkSession object.
            config_path (str): The path to the configuration file.
            file_name (str): The name of the file.
            src_system (str): The source system.

        Attributes:
            spark (SparkSession): The SparkSession object.
            source_df (DataFrame): The source DataFrame.
            error_df (DataFrame): The error DataFrame.
            error_columns (List[str]): The list of error columns.
            error_counter (int): The error counter.
            schema_dict (Dict[str, Union[StringType, DateType, IntegerType, FloatType, DoubleType]]): The schema dictionary.
            config (Dict): The configuration dictionary.
            rule_df (pd.DataFrame): The rule DataFrame.
            file_name (str): The name of the file.
            input_columns (List[str]): The list of input columns.
            output_columns (List[str]): The list of output columns.
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

    def read_s3_file(self, file_path: str) -> bytes:
        """
        Reads a file from S3 and returns its content as bytes.

        Args:
            file_path (str): The S3 file path.

        Returns:
            bytes: The content of the file.

        Raises:
            FileNotFoundError: If the file cannot be found in S3 given the path.
        """
        file_res = urlparse(file_path)
        try:
            file_obj = self.s3_resource.Object(file_res.netloc, file_res.path.lstrip("/"))
            return file_obj.get()["Body"].read()
        except ClientError:
            raise FileNotFoundError(f"File cannot be found in S3 given path '{file_path}'")

    def resolve_config(self, env_path: str, config_content: Any) -> Dict[str, Any]:
        """
        Resolves the configuration by replacing placeholders with values from the environment file.

        Args:
            env_path (str): The path to the environment file.
            config_content (Any): The content of the configuration file.

        Returns:
            Dict[str, Any]: The resolved configuration as a dictionary.

        Examples:
            >>> my_class = MyClass()
            >>> env_path = "path/to/env.json"
            >>> config_content = "<env> <_env> <bucket_name> <account>"
            >>> my_class.resolve_config(env_path, config_content)
            {
                "env": "production",
                "_env": "prod",
                "bucket_name": "my_bucket",
                "account": "1234567890"
            }
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
    def is_float(element: Any) -> bool:
        """
        Checks if the given element can be converted to a float.

        Args:
            element (Any): The element to be checked.

        Returns:
            bool: True if the element can be converted to a float, False otherwise.

        Examples:
            >>> MyClass.is_float(3.14)
            True
            >>> MyClass.is_float("3.14")
            True
            >>> MyClass.is_float("hello")
            False
        """
        try:
            float(element)
            return True
        except ValueError:
            return False

    def limit_finder(self, input_col: str, rule_value: Union[str, float]) -> Optional[Union[float, f.Column]]:
        """
        Finds the limit value based on the given rule_value.

        Args:
            input_col (str): The input column name.
            rule_value (str or float): The rule value to determine the limit.

        Returns:
            float or f.Column or None: The limit value as a float, a pyspark.sql.functions.Column, or None if not found.

        Examples:
            >>> my_class = MyClass()
            >>> my_class.limit_finder("input_column", "3.5")
            3.5
            >>> my_class.limit_finder("input_column", "other_column")
            f.col("other_column")
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

    def columns_to_check(self, criteria: str) -> List[Any]:
        """
        Returns a list of column indices that meet the given criteria.

        Args:
            criteria (str): The criteria to filter the columns.

        Returns:
            List[Any]: A list of column indices that meet the given criteria.

        Examples:
            Assuming `self.rule_df` is a DataFrame with the following structure:
                A    B    C
            0  1.0  NaN  3.0
            1  4.0  5.0  NaN

            >>> obj = MyClass()
            >>> obj.columns_to_check('A')
            [0]
            >>> obj.columns_to_check('B')
            [1]
        """
        return self.rule_df[(self.rule_df[criteria]).notna()].index

    def add_error_col(self, error_msg: str, condition: Column, error_col_name: str) -> None:
        """
        Adds an error column to the source DataFrame based on the given condition.

        Args:
            error_msg (str): The error message to be added in the error column.
            condition (Column): The condition to be checked for each row in the source DataFrame.
            error_col_name (str): The name of the error column to be added.

        Returns:

            None

        """
        if condition is not None and error_col_name and error_msg:
            col_condition = f.when(condition, f.lit(error_msg)).otherwise(f.lit(None))
            error_col_name = error_col_name + str(self.error_counter)
            self.source_df = self.source_df.withColumn(error_col_name, col_condition)
            self.error_columns.append(f.col(error_col_name))
            self.error_counter += 1
        return None

    def data_type_check(self, input_col: str) -> None:
        """
        Checks the data type of a column in the source DataFrame and adds an error column if the data type does not match the expected data type.

        Args:
            input_col (str): The name of the input column to check.

        Returns:
            None

        Examples:
            >>> your_class_instance = YourClassName()
            >>> your_class_instance.data_type_check("column_name")
        """
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
    def null_cond_syntax(self, input_col: str) -> Column:
        """
        Returns a Column object representing a condition where the input column is either an empty string or null.

        Args:
            input_col (str): The name of the input column.

        Returns:
            Column: A Column object representing the condition.

        Examples:
            >>> df = spark.createDataFrame([(1, ""), (2, None), (3, "A")], ["id", "value"])
            >>> my_class = MyClass()
            >>> df.filter(my_class.null_cond_syntax("value")).show()
            +---+-----+
            | id|value|
            +---+-----+
            |  1|     |
            |  2| null|
            +---+-----+
        """
        return (f.col(input_col) == "") | (f.col(input_col).isNull())

    # ...
    def null_check(self, input_col: str) -> None:
        """
        Checks if the input column is null and adds an error message if it is.

        Args:
            input_col (str): The name of the input column to check for null values.

        Returns:
            None

        Examples:
            >>> your_class_instance.null_check("column_name")
            start null_check
            [column_name] null check is done.
        """
        print("start null_check")
        if not math.isnan(self.rule_df.loc[input_col, "nullable"]):
            return
        null_condition = self.null_cond_syntax(input_col)
        null_error_msg = f"null_FAIL: Column [{input_col}] cannot be null"
        self.add_error_col(error_msg=null_error_msg, condition=null_condition, error_col_name=input_col + " null_check")
        logger.info(f"[{input_col}] null check is done.")

    def sum_check_syntax(self, input_col1: str, input_col2: str, syntax_value: Any) -> Any:
        """
        Checks if the sum of the values in the specified columns is not equal to the syntax value.

        Args:
            input_col1 (str): The name of the first input column.
            input_col2 (str): The name of the second input column.
            syntax_value (Any): The value to compare the sum against.

        Returns:
            Any: A boolean column expression where True indicates the sum is not equal to the syntax value.

        Examples:
            >>> df = spark.createDataFrame([(1, 2, 3), (4, 5, 9), (6, 7, 12)], ["col1", "col2", "syntax_value"])
            >>> my_class = MyClass()
            >>> df.withColumn("sum_check", my_class.sum_check_syntax("col1", "col2", f.col("syntax_value"))).show()
            +----+----+------------+---------+
            |col1|col2|syntax_value|sum_check|
            +----+----+------------+---------+
            |   1|   2|           3|     true|
            |   4|   5|           9|    false|
            |   6|   7|          12|    false|
            +----+----+------------+---------+
        """
        return ~(f.col(input_col1) + f.col(input_col2) != syntax_value)

    def conditional_cond_syntax(self, input_col: str, condition_column: str, conditional_variables: Union[str, float]) -> Tuple[str, str]:
        """
        Returns a conditional condition and message based on the input parameters.

        Args:
            input_col (str): The input column name.
            condition_column (str): The condition column name.
            conditional_variables (str or float): The conditional variables, either a string or a float.

        Returns:
            Tuple[str, str]: A tuple containing the conditional condition and message.

        Examples:
            >>> my_class = MyClass()
            >>> my_class.conditional_cond_syntax("input_col", "condition_column", "__NOT__NULL__")
            ('input_col is not null,', 'input_col is not null,')
            >>> my_class.conditional_cond_syntax("input_col", "condition_column", 5.0)
            ('[input_col] and [condition_column] sum is not equal to 5.0', '[input_col] and [condition_column] sum is not equal to 5.0')
            >>> my_class.conditional_cond_syntax("input_col", "condition_column", "A,B,__NOT__C")
            ('[input_col] is in category (["A", "B"]),', '[input_col] is in category (["A", "B"]),')
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

    # ... other methods and attributes ...

    def conditional_check(self, input_col: str) -> None:
        """
        Performs a conditional check on the input column based on the rules defined in the rule_df DataFrame.

        Args:
            input_col (str): The name of the input column to perform the conditional check on.

        Returns:
            None

        Raises:
            None

        Note:
            This method assumes that the following attributes are available in the class:
            - rule_df (pd.DataFrame): A DataFrame containing the rules for conditional checks.
            - input_columns (List[str]): A list of input column names.
            - file_name (str): The name of the file being processed.
            - sns_message (List[str]): A list of messages to be sent via SNS.
            - add_error_col (method): A method to add an error column to the DataFrame.
            - conditional_cond_syntax (method): A method to process the conditional syntax.
            - logger (logging.Logger): A logger instance for logging messages.
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

    def range_cond_syntax(self, input_col: str) -> Tuple[str, str, Any]:
        """
        Generates range conditions for the given input column based on the rule dataframe.

        Args:
            input_col (str): The input column name.

        Returns:
            tuple: A tuple containing the minimum string, maximum string, and the output condition.

        Examples:
            Assuming `self.rule_df` is a dataframe with columns "min" and "max" and a row with index "input_col":
            >>> my_instance = MyClass()
            >>> my_instance.range_cond_syntax("input_col")
            (min_str, max_str, output_cond)
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

    # Other methods and attributes of the class

    def range_check(self, input_col: str) -> None:
        """
        Checks if the values in the input column are within the specified range and adds an error column if not.

        Args:
            input_col (str): The name of the input column to check.

        Returns:
            None

        Examples:
            >>> your_class_instance.range_check("age")
            start range_check
            [age] range check is done.
        """
        print("start range_check")
        min_str, max_str, range_error_cond = self.range_cond_syntax(input_col)
        range_error_cond = range_error_cond & ((f.col(input_col).isNotNull()) | (f.col(input_col) != ""))
        range_error_msg = f"range_FAIL: Column [{input_col}] must be in range ([{min_str}]<{input_col}<[{max_str}])"
        self.add_error_col(
            error_msg=range_error_msg, condition=range_error_cond, error_col_name=input_col + " range_check"
        )
        logger.info(f"[{input_col}] range check is done.")

    def file_check(self, input_col: str) -> Tuple[Union[Column, None], Union[str, None]]:
        """
        Performs a file check on the input column and returns the file condition and error message.

        Args:
            input_col (str): The input column to perform the file check on.

        Returns:
            Tuple[Union[Column, None], Union[str, None]]: A tuple containing the file condition and error message.
                If the file check is successful, the file condition is a Column object and the error message is None.
                If the file check fails, the file condition is None and the error message is a string.

        Examples:
            >>> my_class = MyClass()
            >>> file_cond, file_error_msg = my_class.file_check("column_name")
        """
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
        Checks if the input column values are within the accepted categories.

        Args:
            input_col (str): The name of the input column to be checked.

        Returns:
            None

        Raises:
            None

        Examples:
            >>> your_class_instance.category_check("example_column")
            start category check
            [example_column] category check is done.
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
        Adds a new column "Duplicate_indicator" to the source DataFrame by joining it with the count of duplicates
        for the given input column. Then, returns a boolean Column indicating if the count of duplicates is greater than 1.

        Args:
            input_col (str): The name of the column in the source DataFrame to check for duplicates.

        Returns:
            Column: A boolean Column indicating if the count of duplicates for the given input column is greater than 1.

        Example:
            >>> my_class = MyClass()
            >>> my_class.source_df = spark.createDataFrame([(1, "A"), (2, "A"), (3, "B")], ["id", "value"])
            >>> my_class.source_df.show()
            +---+-----+
            | id|value|
            +---+-----+
            |  1|    A|
            |  2|    A|
            |  3|    B|
            +---+-----+
            >>> duplicate_cond = my_class.duplicate_cond_syntax("value")
            >>> my_class.source_df = my_class.source_df.withColumn("is_duplicate", duplicate_cond)
            >>> my_class.source_df.show()
            +---+-----+------------+
            | id|value|is_duplicate|
            +---+-----+------------+
            |  1|    A|        true|
            |  2|    A|        true|
            |  3|    B|       false|
            +---+-----+------------+
        """
        self.source_df: DataFrame = self.source_df.join(
            broadcast(self.source_df.groupBy(input_col).agg((f.count("*")).alias("Duplicate_indicator"))),
            on=input_col,
            how="inner",
        )
        return f.col("Duplicate_indicator") > 1

    def duplicate_check(self, input_col: str) -> None:
        """
        Checks for duplicate values in the specified input column and adds an error column if duplicates are found.

        Args:
            input_col (str): The name of the input column to check for duplicates.

        Returns:
            None

        Examples:
            >>> your_class_instance = YourClassName()
            >>> your_class_instance.duplicate_check("column_name")
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