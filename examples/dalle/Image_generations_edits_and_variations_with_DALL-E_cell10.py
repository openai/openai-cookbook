# create variations

# call the OpenAI API, using `create_variation` rather than `create`
variation_response = openai.Image.create_variation(
    image=generated_image,  # generated_image is the image generated above
    n=2,
    size="1024x1024",
    response_format="url",
)

# print response
print(variation_response)
