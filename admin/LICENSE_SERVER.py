"""Run behind HTTPS reverse proxy. Admin operations are CLI-only, not public endpoints."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

HOME = Path(os.environ.get("REUP_LICENSE_HOME", "license-server-data")).resolve()


def database():
    HOME.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(HOME / "licenses.sqlite", timeout=20)
    db.execute("CREATE TABLE IF NOT EXISTS licenses (hash TEXT PRIMARY KEY, expires REAL, seats INTEGER, revoked INTEGER DEFAULT 0)")
    db.execute("CREATE TABLE IF NOT EXISTS machines (hash TEXT, machine TEXT, PRIMARY KEY(hash,machine))")
    db.execute("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, license_hash TEXT, machine TEXT, expires REAL, UNIQUE(license_hash,machine))")
    return db


def private_key():
    return Ed25519PrivateKey.from_private_bytes((HOME / "signing.key").read_bytes())


def sign(value):
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return {"payload": base64.b64encode(raw).decode(), "signature": base64.b64encode(private_key().sign(raw)).decode()}


def digest(key):
    return hashlib.sha256(key.strip().encode()).hexdigest()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class Activation(BaseModel):
    refresh: bool=False
    key: str = Field(min_length=8, max_length=256)
    machine: str = Field(pattern=r"^[a-f0-9]{64}$")
    nonce: str = Field(pattern=r"^[a-f0-9]{48}$")


@app.post("/v1/activate")
def activate(body: Activation):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        keyhash = digest(body.key)
        row = db.execute("SELECT expires,seats,revoked FROM licenses WHERE hash=?", (keyhash,)).fetchone()
        if not row or row[2] or row[0] <= time.time():
            raise HTTPException(403, "Key invalid or expired")
        known = db.execute("SELECT 1 FROM machines WHERE hash=? AND machine=?", (keyhash, body.machine)).fetchone()
        count = db.execute("SELECT COUNT(*) FROM machines WHERE hash=?", (keyhash,)).fetchone()[0]
        if not known and count >= row[1]:
            raise HTTPException(403, "Seat limit reached")
        db.execute("INSERT OR IGNORE INTO machines VALUES (?,?)", (keyhash, body.machine))
        lease={"product":"reup-voice-studio","machine":body.machine,"nonce":body.nonce,"expires":min(row[0],time.time()+86400)}
        token=None
        if body.refresh:
            token=secrets.token_urlsafe(48);expires=min(row[0],time.time()+30*86400)
            db.execute('DELETE FROM sessions WHERE license_hash=? AND machine=?',(keyhash,body.machine))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(digest(token),keyhash,body.machine,expires))
            lease.update(refresh_sha256=digest(token),refresh_expires=expires)
        result=sign(lease)
        if token:result['refresh_token']=token
        return result


class Refresh(BaseModel):
    token: str=Field(min_length=32,max_length=256)
    machine: str=Field(pattern=r'^[a-f0-9]{64}$')
    nonce: str=Field(pattern=r'^[a-f0-9]{48}$')


@app.post('/v1/refresh')
def refresh(body: Refresh):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT s.license_hash,s.expires,l.expires,l.revoked FROM sessions s JOIN licenses l ON l.hash=s.license_hash WHERE s.token_hash=? AND s.machine=?',
            (digest(body.token),body.machine)).fetchone()
        if not row or row[1]<=time.time() or row[2]<=time.time() or row[3]:raise HTTPException(403,'Session invalid or expired')
        if not db.execute('SELECT 1 FROM machines WHERE hash=? AND machine=?',(row[0],body.machine)).fetchone():raise HTTPException(403,'Machine reset')
        expires=min(row[2],time.time()+30*86400)
        db.execute('UPDATE sessions SET expires=? WHERE token_hash=?',(expires,digest(body.token)))
        # Reuse the token: a lost HTTP response must not lock the client out.
        return sign({'product':'reup-voice-studio','machine':body.machine,'nonce':body.nonce,
            'expires':min(row[2],time.time()+86400),'refresh_sha256':digest(body.token),'refresh_expires':expires})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "create", "revoke", "reset-machine", "sign-update", "serve"])
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--seats", type=int, default=1)
    parser.add_argument("--key", default="")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--port", type=int, default=18880)
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 only behind a managed HTTPS ingress")
    args = parser.parse_args()
    HOME.mkdir(parents=True, exist_ok=True)
    if args.command == "init":
        path = HOME / "signing.key"
        if path.exists():
            raise SystemExit("Key exists; refusing overwrite")
        key = Ed25519PrivateKey.generate()
        with path.open("xb") as stream:
            stream.write(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))
        path.chmod(0o600)
        public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        print("public_key=" + base64.b64encode(public).decode())
    elif args.command == "create":
        if not 1 <= args.days <= 3650 or not 1 <= args.seats <= 100:
            raise SystemExit("Invalid days/seats")
        key = "RVS-" + secrets.token_urlsafe(24)
        with database() as db:
            db.execute("INSERT INTO licenses(hash,expires,seats) VALUES(?,?,?)", (digest(key), time.time() + args.days * 86400, args.seats))
        print(key)  # Display only once; server database stores the hash.
    elif args.command in {"revoke", "reset-machine"}:
        if not args.key:
            raise SystemExit("--key required")
        with database() as db:
            if args.command == "revoke":
                db.execute("UPDATE licenses SET revoked=1 WHERE hash=?", (digest(args.key),))
            else:
                db.execute('DELETE FROM sessions WHERE license_hash=?',(digest(args.key),))
                db.execute("DELETE FROM machines WHERE hash=?", (digest(args.key),))
    elif args.command == "sign-update":
        if not args.manifest:
            raise SystemExit("--manifest required")
        value = json.loads(args.manifest.read_text(encoding="utf-8"))
        if value.get("product") != "reup-voice-studio" or not re.fullmatch(r"[a-f0-9]{64}", value.get("sha256", "")):
            raise SystemExit("Invalid update manifest")
        target = args.manifest.with_suffix(".signed.json")
        with target.open("x", encoding="utf-8") as stream:
            json.dump(sign(value), stream)
        print(target)
    else:
        private_key()  # Fail closed when not initialized.
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
