# This step creates your model
!openai api fine_tunes.create -t "transactions_grouped_prepared_train.jsonl" -v "transactions_grouped_prepared_valid.jsonl" --compute_classification_metrics --classification_n_classes 5 -m curie

# You can use following command to get fine tuning job status and model name, replace the job name with your job
#!openai api fine_tunes.get -i ft-YBIc01t4hxYBC7I5qhRF3Qdx
