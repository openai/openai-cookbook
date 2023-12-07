
kustoOptions = {"kustoCluster": KUSTO_CLUSTER, "kustoDatabase" :KUSTO_DATABASE, "kustoTable" : KUSTO_TABLE }

# Replace the auth method based on your desired authentication mechanism  - https://github.com/Azure/azure-kusto-spark/blob/master/docs/Authentication.md
access_token=mssparkutils.credentials.getToken(kustoOptions["kustoCluster"])