import boto3
import configparser
import os
import argparse
from botocore.exceptions import NoCredentialsError

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.properties')

def get_s3_client():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=config.get('s3', 'aws_access_key_id'),
            aws_secret_access_key=config.get('s3', 'aws_secret_access_key'),
            region_name=config.get('s3', 'region_name')
        )
        bucket_name = config.get('s3', 'bucket_name')
        return s3_client, bucket_name
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        print(f"Error: Missing S3 configuration in {CONFIG_PATH}: {e}")
        return None, None

def upload_file(local_path, s3_path):
    s3_client, bucket_name = get_s3_client()
    if not s3_client:
        return False

    try:
        s3_client.upload_file(local_path, bucket_name, s3_path)
        print(f"✅ Successfully uploaded {local_path} to s3://{bucket_name}/{s3_path}")
        return True
    except FileNotFoundError:
        print(f"❌ Error: The file {local_path} was not found.")
        return False
    except NoCredentialsError:
        print("❌ Error: AWS credentials not found.")
        return False
    except Exception as e:
        print(f"❌ Error uploading to S3: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload a file to Amazon S3")
    parser.add_argument("local_path", help="Local path of the file to upload")
    parser.add_argument("s3_path", help="S3 destination path (key)")
    
    args = parser.parse_args()
    
    upload_file(args.local_path, args.s3_path)
