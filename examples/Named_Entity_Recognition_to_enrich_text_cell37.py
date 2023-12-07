@retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(5))
def run_openai_task(labels, text):
    messages = [
          {"role": "system", "content": system_message(labels=labels)},
          {"role": "assistant", "content": assisstant_message()},
          {"role": "user", "content": user_message(text=text)}
      ]

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0613",
        messages=messages,
        functions=generate_functions(labels),
        function_call={"name": "enrich_entities"}, 
        temperature=0,
        frequency_penalty=0,
        presence_penalty=0,
    )

    response_message = response["choices"][0]["message"]
    
    available_functions = {"enrich_entities": enrich_entities}  
    function_name = response_message["function_call"]["name"]
    
    function_to_call = available_functions[function_name]
    logging.info(f"function_to_call: {function_to_call}")

    function_args = json.loads(response_message["function_call"]["arguments"])
    logging.info(f"function_args: {function_args}")

    function_response = function_to_call(text, function_args)

    return {"model_response": response, 
            "function_response": function_response}