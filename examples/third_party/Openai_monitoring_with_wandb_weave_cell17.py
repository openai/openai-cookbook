# feel free to substitute your own prompts :)
system_prompts = ["you're extremely flowery and poetic", "you're very direct and precise", "balance brevity with insight"]
prompt_template = 'explain the solution of the following to a {audience}: {equation}'
equations = ['x^2 + 4x + 9 = 0', '15 * (2 - 6) / 4']
audience = ["new student", "math genius"]

for system_prompt in system_prompts:
    for equation in equations:
        for person in audience:
            params = {"equation" : equation, "audience" : person}
            explain_math(system_prompt, prompt_template, params)