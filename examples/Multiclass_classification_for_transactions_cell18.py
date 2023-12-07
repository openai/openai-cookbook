df['combined'] = "Supplier: " + df['Supplier'].str.strip() + "; Description: " + df['Description'].str.strip() + "; Value: " + str(df['Transaction value (£)']).strip()
df.head(2)
