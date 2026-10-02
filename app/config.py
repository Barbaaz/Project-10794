import os

# Override with the DB_CONNECTION_STRING environment variable on other machines
DB_CONNECTION_STRING = os.environ.get(
    "DB_CONNECTION_STRING",
    # Driver 17 returns DATETIME2 as datetime; the old "{SQL Server}" driver returns text
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost\\SQLEXPRESS;"
    "DATABASE=Project10794;"
    "Trusted_Connection=yes;"
)
