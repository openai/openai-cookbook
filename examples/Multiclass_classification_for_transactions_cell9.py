zero_shot_prompt = '''You are a data expert working for the National Library of Scotland.
You are analysing all transactions over £25,000 in value and classifying them into one of five categories.
The five categories are Building Improvement, Literature & Archive, Utility Bills, Professional Services and Software/IT.
If you can't tell what it is, say Could not classify

Transaction:

Supplier: SUPPLIER_NAME
Description: DESCRIPTION_TEXT
Value: TRANSACTION_VALUE

The classification is:'''
