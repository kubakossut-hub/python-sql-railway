from flask import Flask, jsonify, request
import psycopg2
import os

app = Flask(__name__)

def get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])

@app.route("/")
def home():
    return jsonify({"status": "ok", "message": "Python + PostgreSQL on Railway!"})

@app.route("/db-test")
def db_test():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    conn.close()
    return jsonify({"db_status": "connected", "postgres_version": version})

@app.route("/init-db")
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS items (id SERIAL PRIMARY KEY, name VARCHAR(100) NOT NULL, created_at TIMESTAMP DEFAULT NOW())")
    conn.commit()
    conn.close()
    return jsonify({"status": "table items created!"})

@app.route("/items", methods=["GET"])
def get_items():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, created_at FROM items ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return jsonify([{"id": r[0], "name": r[1], "created_at": str(r[2])} for r in rows])

@app.route("/items", methods=["POST"])
def add_item():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO items (name) VALUES (%s) RETURNING id", (data["name"],))
    new_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return jsonify({"id": new_id, "name": data["name"]}), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
