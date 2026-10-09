"""Nightly compressed PostgreSQL backup, authenticated encryption and private S3 retention."""

import base64
import os
import secrets
import subprocess
import tempfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

HEADER = b"LOTNEETI_PG_BACKUP_V1\n"
CHUNK_SIZE = 1024 * 1024
KEEP = {"daily": 7, "weekly": 4, "monthly": 3}


def _key_from_env() -> bytes:
    encoded = os.environ.get("BACKUP_ENCRYPTION_KEY_B64", "")
    try:
        key = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY_B64 must be base64") from exc
    if len(key) != 32:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY_B64 must encode a 32-byte key")
    return key


def _backup_keys(day: date) -> tuple[str, ...]:
    iso_year, iso_week, _ = day.isocalendar()
    return (
        f"backups/postgres/daily/{day.isoformat()}.dump.gcm",
        f"backups/postgres/weekly/{iso_year}-W{iso_week:02d}.dump.gcm",
        f"backups/postgres/monthly/{day:%Y-%m}.dump.gcm",
    )


def _write_encrypted_dump(destination, key: bytes) -> None:
    nonce = secrets.token_bytes(12)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    destination.write(HEADER + nonce)
    process = subprocess.Popen(
        ["pg_dump", "-Fc", "-Z", "9", "--no-owner"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdout is not None
    try:
        while chunk := process.stdout.read(CHUNK_SIZE):
            destination.write(encryptor.update(chunk))
        process.stdout.close()
        if process.wait() != 0:
            raise RuntimeError("pg_dump failed; no backup uploaded")
        destination.write(encryptor.finalize())
        destination.write(encryptor.tag)
        destination.flush()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def _prune(s3, bucket: str, folder: str, keep: int) -> None:
    prefix = f"backups/postgres/{folder}/"
    keys = []
    continuation = None
    while True:
        request = {"Bucket": bucket, "Prefix": prefix}
        if continuation:
            request["ContinuationToken"] = continuation
        page = s3.list_objects_v2(**request)
        keys.extend(
            item["Key"] for item in page.get("Contents", []) if item["Key"].endswith(".dump.gcm")
        )
        continuation = page.get("NextContinuationToken")
        if not continuation:
            break
    old = sorted(keys)[:-keep]
    for offset in range(0, len(old), 1000):
        s3.delete_objects(
            Bucket=bucket,
            Delete={
                "Objects": [{"Key": key} for key in old[offset : offset + 1000]],
                "Quiet": True,
            },
        )


def backup_to_s3(*, s3=None, day: date | None = None) -> tuple[str, ...]:
    """Run once per day; S3 credentials and encryption key come from the host environment."""
    bucket = os.environ.get("BACKUP_S3_BUCKET", "")
    if not bucket:
        raise RuntimeError("BACKUP_S3_BUCKET is required")
    if not all(os.environ.get(name) for name in ("PGHOST", "PGUSER", "PGDATABASE")):
        raise RuntimeError("PGHOST, PGUSER and PGDATABASE are required")
    key = _key_from_env()
    if s3 is None:
        import boto3

        s3 = boto3.client("s3")
    keys = _backup_keys(day or datetime.now(ZoneInfo("Asia/Kolkata")).date())
    with tempfile.NamedTemporaryFile(prefix="lotneeti-backup-", suffix=".gcm") as encrypted:
        _write_encrypted_dump(encrypted, key)
        for object_key in keys:
            s3.upload_file(
                encrypted.name,
                bucket,
                object_key,
                ExtraArgs={"ServerSideEncryption": "AES256"},
            )
    for folder, keep in KEEP.items():
        _prune(s3, bucket, folder, keep)
    return keys


if __name__ == "__main__":
    backup_to_s3()
