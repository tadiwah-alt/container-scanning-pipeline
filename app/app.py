from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
import os

app = Flask(__name__)
CORS(app)

def get_connection():
    return psycopg2.connect(
        host="db",
        database=os.environ['POSTGRES_DB'],
        user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD']
    )



@app.route("/")
def home():
    return "Mini Banking API Running"



@app.route("/accounts")
def accounts():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM accounts;")

    rows = cur.fetchall()

    cur.close()
    conn.close()

    results = []

    for row in rows:
        results.append({
            "id": row[0],
            "name": row[1],
            "balance": row[2]
        })

    return jsonify(results)



@app.route("/balance/<id>")
def balance(id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT balance FROM accounts WHERE id = %s;",
        (id,)
    )

    row = cur.fetchone()

    cur.close()
    conn.close()

    return jsonify({
        "account_id": id,
        "balance": row[0]
    })



@app.route("/deposit", methods=["POST"])
def deposit():

    data = request.get_json()

    account_id = data["account_id"]
    amount = data["amount"]


    if amount <= 0:
        return jsonify({
            "success": False,
            "error": "Amount must be greater than zero"
            
        }), 400

    conn = get_connection()
    cur = conn.cursor()

    # Get current balance
    cur.execute(
        "SELECT balance FROM accounts WHERE id = %s;",
        (account_id,)
    )

    row = cur.fetchone()

    if row is None:
        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "error": "Account not found"
        }), 404

    current_balance = row[0]
    new_balance = current_balance + amount

    # Update balance
    cur.execute(
        "UPDATE accounts SET balance = %s WHERE id = %s;",
        (new_balance, account_id)
    )

    # Record transaction
    cur.execute(
        """
        INSERT INTO transactions
        (from_account_id, to_account_id, transaction_type, amount)
        VALUES (%s, %s, %s, %s);
        """,
        (account_id, account_id, "DEPOSIT", amount)
    )

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "account_id": account_id,
        "deposited": amount,
        "new_balance": new_balance
    })






@app.route("/withdraw", methods=["POST"])
def withdraw():

    data = request.get_json()

    account_id = data["account_id"]
    amount = data["amount"]


    if amount <= 0:
        return jsonify({
            "success": False,
            "error": "Amount must be greater than zero"
            
        }), 400

    conn = get_connection()
    cur = conn.cursor()

    # Get current balance
    cur.execute(
        "SELECT balance FROM accounts WHERE id = %s;",
        (account_id,)
    )

    row = cur.fetchone()

    if row is None:
        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "error": "Account not found"
        }), 404



    current_balance = row[0]

    if current_balance < amount:
            cur.close()
            conn.close()
            
            return jsonify({
                "success": False,
                "error": "Insufficient Funds"
             }), 400
    
    new_balance = current_balance - amount

    # Update balance
    cur.execute(
        "UPDATE accounts SET balance = %s WHERE id = %s;",
        (new_balance, account_id)
    )

    # Record transaction
    cur.execute(
        """
        INSERT INTO transactions
        (from_account_id, to_account_id, transaction_type, amount)
        VALUES (%s, %s, %s, %s);
        """,
        (account_id, account_id, "WITHDRAW", amount)
    )

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "account_id": account_id,
        "withdrawn": amount,
        "new_balance": new_balance
    })



@app.route("/transfer", methods=["POST"])
def transfer():

    data = request.get_json()

    from_id = data["from_account_id"]
    to_id = data["to_account_id"]
    amount = data["amount"]

    # Validate amount
    if amount <= 0:
        return jsonify({
            "success": False,
            "error": "Amount must be greater than zero"
        }), 400

    # Validate accounts are different
    if from_id == to_id:
        return jsonify({
            "success": False,
            "error": "Source and destination accounts must be different"
        }), 400

    conn = get_connection()
    cur = conn.cursor()

    # Verify source account exists
    cur.execute("SELECT balance FROM accounts WHERE id = %s;", (from_id,))
    from_row = cur.fetchone()

    if from_row is None:
        cur.close()
        conn.close()
        return jsonify({
            "success": False,
            "error": "Source account not found"
        }), 404

    # Verify destination account exists
    cur.execute("SELECT balance FROM accounts WHERE id = %s;", (to_id,))
    to_row = cur.fetchone()

    if to_row is None:
        cur.close()
        conn.close()
        return jsonify({
            "success": False,
            "error": "Destination account not found"
        }), 404

    from_balance = from_row[0]
    to_balance = to_row[0]

    # Verify sufficient funds
    if from_balance < amount:
        cur.close()
        conn.close()
        return jsonify({
            "success": False,
            "error": "Insufficient funds"
        }), 400

    new_from_balance = from_balance - amount
    new_to_balance = to_balance + amount

    # Subtract from source
    cur.execute(
        "UPDATE accounts SET balance = %s WHERE id = %s;",
        (new_from_balance, from_id)
    )

    # Add to destination
    cur.execute(
        "UPDATE accounts SET balance = %s WHERE id = %s;",
        (new_to_balance, to_id)
    )

    # Insert TRANSFER transaction
    cur.execute(
        """
        INSERT INTO transactions
        (from_account_id, to_account_id, transaction_type, amount)
        VALUES (%s, %s, %s, %s);
        """,
        (from_id, to_id, "TRANSFER", amount)
    )

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "transferred": amount,
        "from_account": {
            "account_id": from_id,
            "new_balance": new_from_balance
        },
        "to_account": {
            "account_id": to_id,
            "new_balance": new_to_balance
        }
    })



@app.route("/transactions")
def transactions():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id,
               from_account_id,
               to_account_id,
               transaction_type,
               amount,
               created_at
        FROM transactions
        ORDER BY created_at DESC;
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    results = []

    for row in rows:
        results.append({
            "id": row[0],
            "from_account_id": row[1],
            "to_account_id": row[2],
            "transaction_type": row[3],
            "amount": row[4],
            "created_at": row[5]
        })

    return jsonify(results)




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)









