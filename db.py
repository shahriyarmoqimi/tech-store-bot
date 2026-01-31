import os
import psycopg2
from psycopg2 import pool

# Database connection pool setup
# Ensure these environment variables are set in your Vercel project settings
db_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    host=os.environ.get('DB_HOST'),
    database=os.environ.get('DB_NAME'),
    user=os.environ.get('DB_USER'),
    password=os.environ.get('DB_PASS'),
    port=os.environ.get('DB_PORT', 5432)
)

def execute_query(query, params=(), fetch=False, fetch_one=False):
    """
    Executes a SQL query.
    :param query: SQL string
    :param params: Tuple of parameters
    :param fetch: Boolean, if True returns all rows
    :param fetch_one: Boolean, if True returns a single row
    :return: Result data or None
    """
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                result = cur.fetchall()
                return result
            if fetch_one:
                result = cur.fetchone()
                return result
            conn.commit()
            return True
    except Exception as e:
        print(f"Database Error: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            db_pool.putconn(conn)


def check_admin(username, password):
    query = "SELECT id FROM customers WHERE username = %s AND password = %s AND role = 'admin'"
    result = execute_query(query, (username, password), fetch_one=True)
    return True if result else False

