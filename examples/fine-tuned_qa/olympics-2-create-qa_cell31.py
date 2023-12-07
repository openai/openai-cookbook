import matplotlib.pyplot as plt

# plot a histogram, and add axis descriptions and title
out_expanded[(out_expanded['rank'] >=0)&(out_expanded['rank'] <30)]['rank'].hist(bins=29)
plt.xlabel('rank')
plt.ylabel('count')
plt.title('Histogram of ranks of retrieved paragraphs')
plt.show()