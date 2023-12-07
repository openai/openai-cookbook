def list_buckets():
    response = s3_client.list_buckets()
    return json.dumps(response['Buckets'], default=datetime_converter)

def list_objects(bucket, prefix=''):
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return json.dumps(response.get('Contents', []), default=datetime_converter)

def download_file(bucket, key, directory):
    
    filename = os.path.basename(key)
    
    # Resolve destination to the correct file path
    destination = os.path.join(directory, filename)
    
    s3_client.download_file(bucket, key, destination)
    return json.dumps({"status": "success", "bucket": bucket, "key": key, "destination": destination})

def upload_file(source, bucket, key, is_remote_url=False):
    if is_remote_url:
        file_name = os.path.basename(source)
        urlretrieve(source, file_name)
        source = file_name
       
    s3_client.upload_file(source, bucket, key)
    return json.dumps({"status": "success", "source": source, "bucket": bucket, "key": key})

def search_s3_objects(search_name, bucket=None, prefix='', exact_match=True):
    search_name = search_name.lower()
    
    if bucket is None:
        buckets_response = json.loads(list_buckets())
        buckets = [bucket_info["Name"] for bucket_info in buckets_response]
    else:
        buckets = [bucket]

    results = []

    for bucket_name in buckets:
        objects_response = json.loads(list_objects(bucket_name, prefix))
        if exact_match:
            bucket_results = [obj for obj in objects_response if search_name == obj['Key'].lower()]
        else:
            bucket_results = [obj for obj in objects_response if search_name in obj['Key'].lower()]

        if bucket_results:
            results.extend([{"Bucket": bucket_name, "Object": obj} for obj in bucket_results])

    return json.dumps(results)