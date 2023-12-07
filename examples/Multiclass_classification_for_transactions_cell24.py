X_train, X_test, y_train, y_test = train_test_split(
    list(fs_df.babbage_similarity.values), fs_df.Classification, test_size=0.2, random_state=42
)

clf = RandomForestClassifier(n_estimators=100)
clf.fit(X_train, y_train)
preds = clf.predict(X_test)
probas = clf.predict_proba(X_test)

report = classification_report(y_test, preds)
print(report)
