# compare the results of the HNSW index to the FLAT index and time both queries
def time_queries(iterations: int = 10):
    print(" ----- Flat Index ----- ")
    t0 = time.time()
    for i in range(iterations):
        results_flat = search_redis(redis_client, 'modern art in Europe', k=10, print_results=False)
    t0 = (time.time() - t0) / iterations
    results_flat = search_redis(redis_client, 'modern art in Europe', k=10, print_results=True)
    print(f"Flat index query time: {round(t0, 3)} seconds\n")
    time.sleep(1)
    print(" ----- HNSW Index ------ ")
    t1 = time.time()
    for i in range(iterations):
        results_hnsw = search_redis(redis_client, 'modern art in Europe', index_name=HNSW_INDEX_NAME, k=10, print_results=False)
    t1 = (time.time() - t1) / iterations
    results_hnsw = search_redis(redis_client, 'modern art in Europe', index_name=HNSW_INDEX_NAME, k=10, print_results=True)
    print(f"HNSW index query time: {round(t1, 3)} seconds")
    print(" ------------------------ ")
time_queries()