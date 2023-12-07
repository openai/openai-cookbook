#create table
stmt = """
CREATE TABLE IF NOT EXISTS winter_wikipedia2.winter_olympics_2022 (
    id INT PRIMARY KEY,
    text TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
    embedding BLOB
);"""

cur.execute(stmt)
