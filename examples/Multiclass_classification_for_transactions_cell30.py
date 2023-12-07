classes = list(set(ft_prep_df['Classification']))
class_df = pd.DataFrame(classes).reset_index()
class_df.columns = ['class_id','class']
class_df  , len(class_df)
