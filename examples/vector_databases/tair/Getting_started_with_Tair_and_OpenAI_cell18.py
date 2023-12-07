# Check the data count to make sure all the points have been stored
for index_name in index_names:
    stats = client.tvs_get_index(index_name)
    count = int(stats["current_record_count"]) - int(stats["delete_record_count"])
    print(f"Count in {index_name}:{count}")
