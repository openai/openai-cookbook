for name, is_disc in [('discriminator', True), ('qa', False)]:
    for train_test, dt in [('train', train_df), ('test', test_df)]:
        ft = create_fine_tuning_dataset(dt, discriminator=is_disc, n_negative=1, add_related=True)
        ft.to_json(f'{name}_{train_test}.jsonl', orient='records', lines=True)