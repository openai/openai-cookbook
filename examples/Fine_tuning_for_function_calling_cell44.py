reject_training_list = []
for prompt in reject_list:

    #Adjust formatting
    reject_training_list.append({"messages": [{"role":"system","content":DRONE_SYSTEM_PROMPT
                                    },{"role":"user","content": prompt},
                        {"role":"assistant","function_call": {"name": "reject_request","arguments": "{}"}}],
                        "functions":function_list})
