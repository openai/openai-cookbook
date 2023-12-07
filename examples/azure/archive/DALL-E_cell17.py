generation_response = openai.Image.create(
    prompt='A cyberpunk monkey hacker dreaming of a beautiful bunch of bananas, digital art',
    size='1024x1024',
    n=2
)

print(generation_response)