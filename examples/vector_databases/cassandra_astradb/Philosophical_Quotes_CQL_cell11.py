# Your database's Secure Connect Bundle zip file is needed:
if IS_COLAB:
    print('Please upload your Secure Connect Bundle zipfile: ')
    uploaded = files.upload()
    if uploaded:
        astraBundleFileTitle = list(uploaded.keys())[0]
        ASTRA_DB_SECURE_BUNDLE_PATH = os.path.join(os.getcwd(), astraBundleFileTitle)
    else:
        raise ValueError(
            'Cannot proceed without Secure Connect Bundle. Please re-run the cell.'
        )
else:
    # you are running a local-jupyter notebook:
    ASTRA_DB_SECURE_BUNDLE_PATH = input("Please provide the full path to your Secure Connect Bundle zipfile: ")

ASTRA_DB_APPLICATION_TOKEN = getpass("Please provide your Database Token ('AstraCS:...' string): ")
ASTRA_DB_KEYSPACE = input("Please provide the Keyspace name for your Database: ")