import base64
from datetime import date, timedelta
from io import BytesIO
from types import SimpleNamespace

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ops import backup, restore


class FakeProcess:
    def __init__(self, data, exit_code=0):
        self.stdout = BytesIO(data)
        self.exit_code = exit_code

    def wait(self):
        return self.exit_code

    def poll(self):
        return self.exit_code


class FakeS3:
    def __init__(self):
        self.objects = {}

    def upload_file(self, path, bucket, key, *, ExtraArgs):
        assert bucket == "synthetic-private-bucket"
        assert ExtraArgs == {"ServerSideEncryption": "AES256"}
        with open(path, "rb") as source:
            self.objects[key] = source.read()

    def list_objects_v2(self, *, Bucket, Prefix, **kwargs):
        assert Bucket == "synthetic-private-bucket"
        return {"Contents": [{"Key": key} for key in self.objects if key.startswith(Prefix)]}

    def delete_objects(self, *, Bucket, Delete):
        assert Bucket == "synthetic-private-bucket"
        for item in Delete["Objects"]:
            del self.objects[item["Key"]]

    def download_file(self, bucket, key, path):
        assert bucket == "synthetic-private-bucket"
        with open(path, "wb") as destination:
            destination.write(self.objects[key])


def _settings(monkeypatch):
    key = b"s" * 32
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY_B64", base64.b64encode(key).decode())
    monkeypatch.setenv("BACKUP_S3_BUCKET", "synthetic-private-bucket")
    monkeypatch.setenv("PGHOST", "synthetic-db")
    monkeypatch.setenv("PGUSER", "synthetic-user")
    monkeypatch.setenv("PGDATABASE", "synthetic-database")
    return key


def test_encrypted_backup_uploads_private_objects_and_prunes_retention(monkeypatch):
    key = _settings(monkeypatch)
    synthetic_dump = b"synthetic pg_dump custom archive" * 10
    monkeypatch.setattr(
        backup.subprocess, "Popen", lambda *args, **kwargs: FakeProcess(synthetic_dump)
    )
    s3 = FakeS3()
    start = date(2026, 9, 1)
    for offset in range(110):
        backup.backup_to_s3(s3=s3, day=start + timedelta(days=offset))
    daily = [key for key in s3.objects if "/daily/" in key]
    weekly = [key for key in s3.objects if "/weekly/" in key]
    monthly = [key for key in s3.objects if "/monthly/" in key]
    assert len(daily) == 7
    assert len(weekly) == 4
    assert len(monthly) == 3
    encrypted = s3.objects[daily[-1]]
    assert synthetic_dump not in encrypted
    nonce_start = len(backup.HEADER)
    nonce = encrypted[nonce_start : nonce_start + 12]
    ciphertext = encrypted[nonce_start + 12 : -16]
    tag = encrypted[-16:]
    decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
    assert decryptor.update(ciphertext) + decryptor.finalize() == synthetic_dump


def test_failed_dump_never_uploads_a_partial_backup(monkeypatch):
    _settings(monkeypatch)
    monkeypatch.setattr(
        backup.subprocess, "Popen", lambda *args, **kwargs: FakeProcess(b"partial", 1)
    )
    s3 = FakeS3()
    with pytest.raises(RuntimeError, match="pg_dump failed"):
        backup.backup_to_s3(s3=s3, day=date(2026, 9, 27))
    assert s3.objects == {}


def test_restore_authenticates_before_touching_an_isolated_database(monkeypatch):
    _settings(monkeypatch)
    archive_bytes = b"synthetic PostgreSQL custom archive"
    monkeypatch.setattr(
        backup.subprocess, "Popen", lambda *args, **kwargs: FakeProcess(archive_bytes)
    )
    s3 = FakeS3()
    object_key = backup.backup_to_s3(s3=s3, day=date(2026, 9, 27))[0]
    restored = []

    def fake_pg_restore(command, **kwargs):
        assert command[:4] == ["pg_restore", "--no-owner", "--no-privileges", "--dbname"]
        assert command[4] == "lotneeti_restore_drill"
        with open(command[5], "rb") as source:
            restored.append(source.read())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(restore.subprocess, "run", fake_pg_restore)
    restore.restore_from_s3(s3=s3, object_key=object_key, database="lotneeti_restore_drill")
    assert restored == [archive_bytes]
    with pytest.raises(RuntimeError, match="separate"):
        restore.restore_from_s3(s3=s3, object_key=object_key, database="production")
    encrypted = bytearray(s3.objects[object_key])
    encrypted[-1] ^= 1
    s3.objects[object_key] = bytes(encrypted)
    with pytest.raises(InvalidTag):
        restore.restore_from_s3(s3=s3, object_key=object_key, database="lotneeti_restore_drill")
    assert restored == [archive_bytes]
