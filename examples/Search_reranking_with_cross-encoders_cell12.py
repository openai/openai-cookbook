result = response["choices"][0]
print(f"Result was {result['text']}")
print(f"Logprobs was {result['logprobs']['token_logprobs'][0]}")
print("\nBelow is the full logprobs object\n\n")
print(result["logprobs"])