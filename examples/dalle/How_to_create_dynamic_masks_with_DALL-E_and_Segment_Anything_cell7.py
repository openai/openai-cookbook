# Generate your images
generation_response = openai.Image.create(
    prompt=dalle_prompt,
    n=3,
    size="1024x1024",
    response_format="url",
)