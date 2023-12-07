# edit an image

# call the OpenAI API
edit_response = openai.Image.create_edit(
    image=open(chosen_image, "rb"),  # from the generation section
    mask=open(os.path.join(mask_dir, "new_mask.png"), "rb"),  # from right above
    prompt="Brilliant leather Lederhosen with a formal look, detailed, intricate, photorealistic",  # provide a prompt to fill the space
    n=3,
    size="1024x1024",
    response_format="url",
)

edit_filepaths = process_dalle_images(edit_response, "edits", edit_image_dir)
