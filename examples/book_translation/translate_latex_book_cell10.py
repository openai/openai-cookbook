dest_language = "English"

translated_chunks = []
for i, chunk in enumerate(chunks):
    print(str(i+1) + " / " + str(len(chunks)))
    # translate each chunk
    translated_chunks.append(translate_chunk(chunk, engine='text-davinci-002', dest_language=dest_language))

# join the chunks together
result = '\n\n'.join(translated_chunks)

# save the final result
with open(f"data/geometry_{dest_language}.tex", "w") as f:
    f.write(result)