import os
import oracledb
from dotenv import load_dotenv
from array import array

#start thick mode (for vector)
oracledb.init_oracle_client(lib_dir=r"C:\oracle\instantclient-basic-windows.x64-23.26.0.0.0\instantclient_23_0")


# load .env
load_dotenv()

ORACLE_USER = os.getenv("ORACLE_USER")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD")
ORACLE_DSN = os.getenv("ORACLE_DSN")


def get_connection():
    """
    Create and return an Oracle DB connection
    """
    return oracledb.connect(
        user=ORACLE_USER,
        password=ORACLE_PASSWORD,
        dsn=ORACLE_DSN
    )


def test_connection():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 'Oracle connection OK' FROM dual")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0]


def insert_document(content, embedding):
    #"""
    #Insert a document and its embedding into the documents table
    #"""
    conn = get_connection()
    cursor = conn.cursor()

    #tell oracle this is a vector
    cursor.setinputsizes(
        content=oracledb.DB_TYPE_CLOB,
        embedding=oracledb.DB_TYPE_VECTOR
    )

    #the key
    embedding_array = array("f", embedding)

    cursor.execute(
        """
        INSERT INTO documents (content, embedding)
        VALUES (:content, :embedding)
        """,
        {
            "content": content,
            "embedding": embedding # # list of fkoat 32
        }
    )

    conn.commit()
    cursor.close()
    conn.close()