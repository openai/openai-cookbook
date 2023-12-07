# Example prompt - 
template_prompt=f'''Extract key pieces of information from this regulation document.
If a particular piece of information is not present, output \"Not specified\".
When you extract a key piece of information, include the closest page number.
Use the following format:\n0. Who is the author\n1. How is a Minor Overspend Breach calculated\n2. How is a Major Overspend Breach calculated\n3. Which years do these financial regulations apply to\n\nDocument: \"\"\"{document}\"\"\"\n\n0. Who is the author: Tom Anderson (Page 1)\n1.'''
print(template_prompt)