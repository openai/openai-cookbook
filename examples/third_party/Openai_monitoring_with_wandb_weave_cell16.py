def explain_math(system_prompt, prompt_template, params):
    openai.ChatCompletion.create(model=OPENAI_MODEL,
                             messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": prompt_template.format(**params)},
                                ],
                             # you can add additional attributes to the logged record
                             # see the monitor_api notebook for more examples
                             monitor_attributes={
                                 'system_prompt': system_prompt,
                                 'prompt_template': prompt_template,
                                 'params': params
                             })