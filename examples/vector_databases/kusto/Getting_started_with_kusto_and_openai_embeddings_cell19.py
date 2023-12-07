# Write data to a Kusto table
sparkDF.write. \
format("com.microsoft.kusto.spark.synapse.datasource"). \
option("kustoCluster",kustoOptions["kustoCluster"]). \
option("kustoDatabase",kustoOptions["kustoDatabase"]). \
option("kustoTable", kustoOptions["kustoTable"]). \
option("accessToken", access_token). \
option("tableCreateOptions", "CreateIfNotExist").\
mode("Append"). \
save()
