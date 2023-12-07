def generate_points_from_dataframe(df: pd.DataFrame) -> List[PointStruct]:
    batch_size = 512
    questions = df["question"].tolist()
    total_batches = len(questions) // batch_size + 1
    
    pbar = tqdm(total=len(questions), desc="Generating embeddings")
    
    # Generate embeddings in batches to improve performance
    embeddings = []
    for i in range(total_batches):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, len(questions))
        batch = questions[start_idx:end_idx]
        
        batch_embeddings = embedding_model.embed(batch, batch_size=batch_size)
        embeddings.extend(batch_embeddings)
        pbar.update(len(batch))
        
    pbar.close()
    
    # Convert embeddings to list of lists
    embeddings_list = [embedding.tolist() for embedding in embeddings]
    
    # Create a temporary DataFrame to hold the embeddings and existing DataFrame columns
    temp_df = df.copy()
    temp_df["embeddings"] = embeddings_list
    temp_df["id"] = temp_df.index
    
    # Generate PointStruct objects using DataFrame apply method
    points = temp_df.progress_apply(
        lambda row: PointStruct(
            id=row["id"],
            vector=row["embeddings"],
            payload={
                "question": row["question"],
                "title": row["title"],
                "context": row["context"],
                "is_impossible": row["is_impossible"],
                "answers": row["answers"],
            },
        ),
        axis=1,
    ).tolist()

    return points

points = generate_points_from_dataframe(train_df)