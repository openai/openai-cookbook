# Example prompt - 
document = '<document>'
template_prompt=f'''Extract key pieces of information from this regulation document.
If a particular piece of information is not present, output \"Not specified\".
When you extract a key piece of information, include the closest page number.
Use the following format:\n0. Who is the author\n1. What is the amount of the "Power Unit Cost Cap" in USD, GBP and EUR\n2. What is the value of External Manufacturing Costs in USD\n3. What is the Capital Expenditure Limit in USD\n\nDocument: \"\"\"{document}\"\"\"\n\n0. Who is the author: Tom Anderson (Page 1)\n1.'''
print(template_prompt)