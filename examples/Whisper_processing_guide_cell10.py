# Define function to remove non-ascii characters
def remove_non_ascii(text):
    return ''.join(i for i in text if ord(i)<128)
