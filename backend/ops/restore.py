"""Authenticate and restore a backup into an isolated PostgreSQL database."""

import os
import subprocess
import tempfile

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ops.backup import CHUNK_SIZE, HEADER, _key_from_env


def decrypt_archive(source, destination, key: bytes) -> None:
    if source.read(len(HEADER)) != HEADER:
        raise RuntimeError("Unknown backup format")
    nonce = source.read(12)
    if len(nonce) != 12:
        raise RuntimeError("Incomplete backup nonce")
    body_start = source.tell()
    source.seek(0, os.SEEK_END)
    end = source.tell()
    if end - body_start < 16:
        raise RuntimeError("Incomplete backup authentication tag")
    source.seek(end - 16)
    tag = source.read(16)
    source.seek(body_start)
    remaining = end - body_start - 16
    decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
    while remaining:
        chunk = source.read(min(CHUNK_SIZE, remaining))
        if not chunk:
            raise RuntimeError("Incomplete backup ciphertext")
        destination.write(decryptor.update(chunk))
        remaining -= len(chunk)
    destination.write(decryptor.finalize())
    destination.flush()


def restore_from_s3(*, s3=None, object_key: str | None = None, database: str | None = None) -> None:
    bucket = os.environ.get("BACKUP_S3_BUCKET", "")
    if not bucket:
        raise RuntimeError("BACKUP_S3_BUCKET is required")
    key = object_key or os.environ.get("RESTORE_S3_KEY", "")
    target = database or os.environ.get("RESTORE_DATABASE", "")
    if not key.startswith("backups/postgres/") or not key.endswith(".dump.gcm"):
        raise RuntimeError("RESTORE_S3_KEY must name a LotNeeti PostgreSQL backup")
    if not target.startswith("lotneeti_restore_") or target == os.environ.get("PGDATABASE"):
        raise RuntimeError("Restore target must be a separate lotneeti_restore_ database")
    encryption_key = _key_from_env()
    if s3 is None:
        import boto3

        s3 = boto3.client("s3")
    with tempfile.NamedTemporaryFile(prefix="lotneeti-download-", suffix=".gcm") as encrypted:
        s3.download_file(bucket, key, encrypted.name)
        with tempfile.NamedTemporaryFile(prefix="lotneeti-restore-", suffix=".dump") as archive:
            with open(encrypted.name, "rb") as source:
                decrypt_archive(source, archive, encryption_key)
            result = subprocess.run(
                ["pg_restore", "--no-owner", "--no-privileges", "--dbname", target, archive.name],
                check=False,
                capture_output=True,
            )
            if result.returncode != 0:
                raise RuntimeError("pg_restore failed; inspect isolated target database")


if __name__ == "__main__":
    restore_from_s3()
