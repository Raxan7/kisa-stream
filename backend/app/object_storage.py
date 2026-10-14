"""Private S3-compatible R2 storage for release playback.

Never place R2 credentials in the mobile app. The server signs short-lived URLs
only after checking the viewer's account and entitlement.
"""
import os
from pathlib import Path

from botocore.config import Config


def enabled():
    return os.getenv('VIDEO_STORAGE', 'local').lower() == 'r2'


def bucket():
    value = os.getenv('R2_BUCKET', '').strip()
    if not value:
        raise RuntimeError('Missing R2_BUCKET')
    return value


def client():
    import boto3
    account = os.getenv('R2_ACCOUNT_ID', '').strip()
    key = os.getenv('R2_ACCESS_KEY_ID', '').strip()
    secret = os.getenv('R2_SECRET_ACCESS_KEY', '').strip()
    if not all((account, key, secret)):
        raise RuntimeError('Missing R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY')
    return boto3.client(
        's3',
        endpoint_url=f'https://{account}.r2.cloudflarestorage.com',
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name='auto',
        config=Config(signature_version='s3v4', retries={'max_attempts': 3, 'mode': 'standard'}),
    )


def valid_key(name):
    # UUID-named MP4s are generated server-side, never trust arbitrary storage paths.
    return isinstance(name, str) and name.endswith('.mp4') and len(name) <= 255 and \
        '/' not in name and '\\' not in name and '..' not in name


def exists(name):
    if not valid_key(name):
        return False
    from botocore.exceptions import ClientError
    try:
        client().head_object(Bucket=bucket(), Key=f'episodes/{name}')
        return True
    except ClientError as exc:
        if exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 404:
            return False
        raise


def upload(path: Path, name: str):
    if not valid_key(name):
        raise ValueError('Invalid object filename')
    client().upload_file(str(path), bucket(), f'episodes/{name}', ExtraArgs={
        'ContentType': 'video/mp4',
        'CacheControl': 'private, max-age=1200',
    })


def presign(name: str, lifetime: int = 1200):
    if not valid_key(name):
        raise ValueError('Invalid object filename')
    return client().generate_presigned_url(
        'get_object', Params={'Bucket': bucket(), 'Key': f'episodes/{name}'}, ExpiresIn=lifetime,
    )
