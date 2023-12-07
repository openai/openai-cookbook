# This functions checks that your classes all appear in both prepared files
# If they don't, the fine-tuned model creation will fail
check_finetune_classes('transactions_grouped_prepared_train.jsonl','transactions_grouped_prepared_valid.jsonl')
