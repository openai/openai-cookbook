# This step is unnecessary if you have a number of observations in each class
# In our case we don't, so we shuffle the data to give us a better chance of getting equal classes in our train and validation sets
# Our fine-tuned model will error if we have less classes in the validation set, so this is a necessary step

import random

labels = [x for x in ft_df_with_class['class_id']]
text = [x for x in ft_df_with_class['prompt']]
ft_df = pd.DataFrame(zip(text, labels), columns = ['prompt','class_id']) #[:300]
ft_df.columns = ['prompt','completion']
ft_df['ordering'] = ft_df.apply(lambda x: random.randint(0,len(ft_df)), axis = 1)
ft_df.set_index('ordering',inplace=True)
ft_df_sorted = ft_df.sort_index(ascending=True)
ft_df_sorted.head()
