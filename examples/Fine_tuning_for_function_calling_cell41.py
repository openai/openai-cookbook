training_examples = []
for prompt in training_examples_unformatted:
    #adjust formatting for training data specs
    try:
        prompt["Input"] = ast.literal_eval(prompt["Input"])
    except:
        continue
    prompt['Input']['arguments']=json.dumps(prompt['Input']['arguments'])
    for p in prompt['Prompt']:
        training_examples.append({"messages": [{"role":"system","content":DRONE_SYSTEM_PROMPT
                                        },{"role":"user","content": p},
                            {"role":"assistant","function_call": prompt['Input']}],
                            "functions":function_list})
