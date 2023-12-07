import pandas as pd
df = pd.read_csv('olympics-data/olympics_sections.csv')
df['context'] = df.title + "\n" + df.heading + "\n\n" + df.content
df.head()