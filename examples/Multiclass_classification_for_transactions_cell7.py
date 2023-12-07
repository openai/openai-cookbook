def request_completion(prompt):

    completion_response =   openai.completions.create(
                            prompt=prompt,
                            temperature=0,
                            max_tokens=5,
                            top_p=1,
                            frequency_penalty=0,
                            presence_penalty=0,
                            model=COMPLETIONS_MODEL
                            )

    return completion_response

def classify_transaction(transaction,prompt):

    prompt = prompt.replace('SUPPLIER_NAME',transaction['Supplier'])
    prompt = prompt.replace('DESCRIPTION_TEXT',transaction['Description'])
    prompt = prompt.replace('TRANSACTION_VALUE',str(transaction['Transaction value (£)']))

    classification = request_completion(prompt).choices[0].text.replace('\n','')

    return classification

# This function takes your training and validation outputs from the prepare_data function of the Finetuning API, and
# confirms that each have the same number of classes.
# If they do not have the same number of classes the fine-tune will fail and return an error

def check_finetune_classes(train_file,valid_file):

    train_classes = set()
    valid_classes = set()
    with open(train_file, 'r') as json_file:
        json_list = list(json_file)
        print(len(json_list))

    for json_str in json_list:
        result = json.loads(json_str)
        train_classes.add(result['completion'])
        #print(f"result: {result['completion']}")
        #print(isinstance(result, dict))

    with open(valid_file, 'r') as json_file:
        json_list = list(json_file)
        print(len(json_list))

    for json_str in json_list:
        result = json.loads(json_str)
        valid_classes.add(result['completion'])
        #print(f"result: {result['completion']}")
        #print(isinstance(result, dict))

    if len(train_classes) == len(valid_classes):
        print('All good')

    else:
        print('Classes do not match, please prepare data again')
