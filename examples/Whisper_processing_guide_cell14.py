# Define function to fix product mispellings
def product_assistant(ascii_transcript):
    system_prompt = """You are an intelligent assistant specializing in financial products;
    your task is to process transcripts of earnings calls, ensuring that all references to
     financial products and common financial terms are in the correct format. For each
     financial product or common term that is typically abbreviated as an acronym, the full term 
    should be spelled out followed by the acronym in parentheses. For example, '401k' should be
     transformed to '401(k) retirement savings plan', 'HSA' should be transformed to 'Health Savings Account (HSA)'
    , 'ROA' should be transformed to 'Return on Assets (ROA)', 'VaR' should be transformed to 'Value at Risk (VaR)'
, and 'PB' should be transformed to 'Price to Book (PB) ratio'. Similarly, transform spoken numbers representing 
financial products into their numeric representations, followed by the full name of the product in parentheses. 
For instance, 'five two nine' to '529 (Education Savings Plan)' and 'four zero one k' to '401(k) (Retirement Savings Plan)'.
 However, be aware that some acronyms can have different meanings based on the context (e.g., 'LTV' can stand for 
'Loan to Value' or 'Lifetime Value'). You will need to discern from the context which term is being referred to 
and apply the appropriate transformation. In cases where numerical figures or metrics are spelled out but do not 
represent specific financial products (like 'twenty three percent'), these should be left as is. Your role is to
 analyze and adjust financial product terminology in the text. Once you've done that, produce the adjusted 
 transcript and a list of the words you've changed"""
    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": ascii_transcript
            }
        ]
    )
    return response
