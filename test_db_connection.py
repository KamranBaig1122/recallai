"""
Test script to verify Supabase database connection
Based on Supabase template
"""
import psycopg2
from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()

# Fetch variables (support both formats)
# Note: Check DB-specific port variables first to avoid conflicts with Django PORT
USER = os.getenv("user") or os.getenv("SUPABASE_DB_USER") or "postgres"
PASSWORD = os.getenv("password") or os.getenv("SUPABASE_DB_PASSWORD") or ""
HOST = os.getenv("host") or os.getenv("SUPABASE_DB_HOST") or ""

# Debug: Check what's actually in .env
print("Checking .env file variables:")
print(f"  os.getenv('user'): {os.getenv('user')}")
print(f"  os.getenv('password'): {'***' if os.getenv('password') else 'None'}")
print(f"  os.getenv('host'): {os.getenv('host')}")
print(f"  os.getenv('dbname'): {os.getenv('dbname')}")
# Prioritize DB port variables, ignore Django PORT variable
DB_PORT = os.getenv("SUPABASE_DB_PORT") or os.getenv("port")
if not DB_PORT or DB_PORT == os.getenv("PORT"):
    # If port matches Django PORT, it's probably wrong, use default
    DB_PORT = "5432"
PORT = DB_PORT
DBNAME = os.getenv("dbname") or os.getenv("SUPABASE_DB_NAME") or "postgres"

# Debug output
print(f"\nEnvironment check:")
print(f"  'user' env var: {os.getenv('user')}")
print(f"  'host' env var: {os.getenv('host')}")
print(f"  'dbname' env var: {os.getenv('dbname')}")
print(f"  'SUPABASE_DB_PORT' env var: {os.getenv('SUPABASE_DB_PORT')}")
print(f"  'port' env var: {os.getenv('port')}")
print(f"  'PORT' env var (Django): {os.getenv('PORT')}")
print(f"  Using Database PORT: {PORT}")

print(f"\n{'='*50}")
print(f"Connection Details:")
print(f"  Host: {HOST}")
print(f"  Port: {PORT}")
print(f"  Database: {DBNAME}")
print(f"  User: {USER}")
print(f"  Password: {'*' * len(PASSWORD) if PASSWORD else 'NOT SET'}")
print(f"{'='*50}\n")

if not HOST:
    print("ERROR: Host is not set! Check your .env file.")
    exit(1)
if not PASSWORD:
    print("WARNING: Password is not set! Check your .env file.")

# Connect to the database
try:
    connection = psycopg2.connect(
        user=USER,
        password=PASSWORD,
        host=HOST,
        port=PORT,
        dbname=DBNAME,
        sslmode='require'  # Supabase requires SSL
    )
    print("Connection successful!")
    
    # Create a cursor to execute SQL queries
    cursor = connection.cursor()
    
    # Example query
    cursor.execute("SELECT NOW();")
    result = cursor.fetchone()
    print("Current Time:", result)
    
    # Close the cursor and connection
    cursor.close()
    connection.close()
    print("Connection closed.")
    
except Exception as e:
    print(f"Failed to connect: {e}")
    print("\nTroubleshooting:")
    print("1. Check your .env file has the correct credentials")
    print("2. Verify network connectivity to Supabase")
    print("3. Check if firewall is blocking the connection")
    print("4. Ensure SSL is enabled (Supabase requires SSL)")

