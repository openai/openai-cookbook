# Load chosen image using opencv
image = cv2.imread(chosen_image)
image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

# Display our chosen image
plt.figure(figsize=(10, 10))
plt.imshow(image)
plt.axis("on")
plt.show()