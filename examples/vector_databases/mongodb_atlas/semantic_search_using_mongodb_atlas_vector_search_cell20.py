query="imaginary characters from outerspace at war with earthlings"
movies = query_results(query, 5)

for movie in movies:
    print(f'Movie Name: {movie["title"]},\nMovie Plot: {movie["plot"]}\n')