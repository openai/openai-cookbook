# Set the pixel coordinates for our "click" to assign masks
input_point = np.array([[525, 325]])
input_label = np.array([1])

# Display the point we've clicked on
plt.figure(figsize=(10, 10))
plt.imshow(image)
show_points(input_point, input_label, plt.gca())
plt.axis("on")
plt.show()