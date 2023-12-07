ft_df_with_class = ft_prep_df.merge(class_df,left_on='Classification',right_on='class',how='inner')

# Adding a leading whitespace onto each completion to help the model
ft_df_with_class['class_id'] = ft_df_with_class.apply(lambda x: ' ' + str(x['class_id']),axis=1)
ft_df_with_class = ft_df_with_class.drop('class', axis=1)

# Adding a common separator onto the end of each prompt so the model knows when a prompt is terminating
ft_df_with_class['prompt'] = ft_df_with_class.apply(lambda x: x['combined'] + '\n\n###\n\n',axis=1)
ft_df_with_class.head()
