import psycopg2

conn = psycopg2.connect(
    "postgresql://twi_dictionary_db_user:63OOHsydah6SLBJeN41CVJkZtLquqOWe@dpg-d4jo9f3e5dus73eo0p3g-a.render.com:5432/twi_dictionary_db"
)

cur = conn.cursor()
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public';")
print(cur.fetchall())

cur.close()
conn.close()
