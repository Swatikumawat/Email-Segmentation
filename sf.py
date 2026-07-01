"""Snowflake connection helper for the Email Segmentation project.
Key-pair auth as SWATIKUMAWAT. Key file rsa_key.p8 sits beside this file.
Usage: python sf.py "SELECT 1"   |   python sf.py -f file.sql
"""
import os, sys
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

HERE = os.path.dirname(os.path.abspath(__file__))
ACCOUNT   = "nua76068.us-east-1"
USER      = "SWATIKUMAWAT"
WAREHOUSE = "EMEA_IN_WH"
DATABASE  = "MODEL_DEV"


def _pk():
    with open(os.path.join(HERE, "rsa_key.p8"), "rb") as f:
        k = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
    return k.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def connect():
    return snowflake.connector.connect(
        account=ACCOUNT, user=USER, private_key=_pk(),
        warehouse=WAREHOUSE, database=DATABASE,
        session_parameters={"QUERY_TAG": "email-seg-build"},
    )


def run(sql):
    conn = connect(); cur = conn.cursor()
    try:
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            cur.execute(stmt)
            cols = [c[0] for c in cur.description] if cur.description else []
            rows = cur.fetchall() if cur.description else []
            print(f"--- {stmt.splitlines()[0][:80]} ---")
            if cols:
                print(cols)
            for r in rows[:50]:
                print(r)
            if not rows and not cols:
                print("(ok)")
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "-f":
        run(open(sys.argv[2], encoding="utf-8").read())
    else:
        run(sys.argv[1])
