import singlestoredb as s2

conn = s2.connect("<user>:<Password>@<host>:3306/")

cur = conn.cursor()
