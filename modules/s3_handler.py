"""
S3 operations for gfd.sh — posts storage and retrieval.
"""
import json
import datetime
import boto3
from zoneinfo import ZoneInfo
from modules.config import require_env

s3 = boto3.client('s3')
S3_BUCKET = require_env('S3_BUCKET')


def read_s3(key):
    """Read an object from S3 and return its content as a string."""
    response = s3.get_object(Bucket=S3_BUCKET, Key=key)
    return response['Body'].read().decode('utf-8')


def write_s3(key, content, content_type='application/json'):
    """Write string content to an S3 object."""
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=content.encode('utf-8'),
        ContentType=content_type,
        StorageClass='INTELLIGENT_TIERING',
    )


def get_posts():
    """Return list of post dicts from posts.json in S3."""
    try:
        data = json.loads(read_s3('posts.json'))
        return data.get('posts', [])
    except s3.exceptions.NoSuchKey:
        return []
    except Exception:
        return []


def save_post(formatted_html):
    """Prepend a new post (pre-rendered HTML) to posts.json in S3."""
    try:
        posts_data = json.loads(read_s3('posts.json'))
    except Exception:
        posts_data = {'posts': []}

    timestamp = datetime.datetime.now(
        ZoneInfo("America/Denver")
    ).strftime("%Y-%m-%d %H:%M:%S %Z")

    posts_data['posts'].insert(0, {
        'timestamp': timestamp,
        'html': formatted_html,
    })

    write_s3('posts.json', json.dumps(posts_data, indent=2))
