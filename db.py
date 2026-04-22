import pyodbc

def get_connection():
    conn = pyodbc.connect(
        "DRIVER={SQL Server};"
        "SERVER=localhost\\SQLEXPRESS;"
        "DATABASE=Project10794;"
        "Trusted_Connection=yes;"
    )
    return conn