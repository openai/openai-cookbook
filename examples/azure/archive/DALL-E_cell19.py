import os
import requests

# First a little setup
image_dir = os.path.join(os.curdir, 'images')
# If the directory doesn't exist, create it
if not os.path.isdir(image_dir):
    os.mkdir(image_dir)

# With the directory in place, we can initialize the image path (note that filetype should be png)
image_path = os.path.join(image_dir, 'generated_image.png')

# Now we can retrieve the generated image
image_url = generation_response["data"][0]["url"]  # extract image URL from response
generated_image = requests.get(image_url).content  # download the image
with open(image_path, "wb") as image_file:
    image_file.write(generated_image)