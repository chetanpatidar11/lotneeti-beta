"""Private S3 export object with a short-lived download URL."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from exports.adapters import ExportArtifact

DOWNLOAD_TTL_SECONDS = 300


class S3ExportStorage:
    def __init__(self, *, client=None, bucket: str | None = None):
        self.bucket = bucket or settings.EXPORT_S3_BUCKET
        if not self.bucket:
            raise ImproperlyConfigured("Set EXPORT_S3_BUCKET before generating exports")
        if client is None:
            import boto3

            client = boto3.client("s3")
        self.client = client

    def put(self, key: str, artifact: ExportArtifact) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=artifact.data,
            ContentType=artifact.content_type,
            CacheControl="private, no-store",
            ServerSideEncryption="AES256",
        )

    def signed_url(self, key: str, *, filename: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=DOWNLOAD_TTL_SECONDS,
        )


def get_export_storage() -> S3ExportStorage:
    return S3ExportStorage()
