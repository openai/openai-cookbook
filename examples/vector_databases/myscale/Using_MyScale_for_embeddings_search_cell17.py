# check count of inserted data
print(f"articles count: {client.command('SELECT count(*) FROM default.articles')}")

# check the status of the vector index, make sure vector index is ready with 'Built' status
get_index_status="SELECT status FROM system.vector_indices WHERE name='article_content_index'"
print(f"index build status: {client.command(get_index_status)}")