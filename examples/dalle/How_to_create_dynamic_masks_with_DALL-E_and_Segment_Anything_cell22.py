# Display your beautiful creations!
%matplotlib inline

# figure size in inches optional
rcParams["figure.figsize"] = 11 ,8

# read images
img_A = mpimg.imread(edit_filepaths[0])
img_B = mpimg.imread(edit_filepaths[1])
img_C = mpimg.imread(edit_filepaths[2])

# display images
fig, ax = plt.subplots(1,3)
[a.axis("off") for a in ax]
ax[0].imshow(img_A)
ax[1].imshow(img_B)
ax[2].imshow(img_C)