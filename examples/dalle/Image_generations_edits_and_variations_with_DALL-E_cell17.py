# edit an image

# call the OpenAI API
edit_response = openai.Image.create_edit(
    image=open(generated_image_filepath, "rb"),  # from the generation section
    mask=open(mask_filepath, "rb"),  # from right above
    prompt=prompt,  # from the generation section
    n=1,
    size="1024x1024",
    response_format="url",
)

# print response
print(edit_response)
