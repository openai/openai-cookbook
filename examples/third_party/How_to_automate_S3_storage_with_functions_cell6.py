# Optional - if you had issues loading the environment file, you can set the AWS values using the below code
# os.environ['AWS_ACCESS_KEY_ID'] = ''
# os.environ['AWS_SECRET_ACCESS_KEY'] = ''

# Create S3 client
s3_client = boto3.client('s3')