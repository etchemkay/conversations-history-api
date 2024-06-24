import boto3
import json
from fastapi import HTTPException
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError

class S3Utils:
    def __init__(self, bucket_name: str):
        self.s3_client = boto3.client('s3')
        self.bucket_name = bucket_name

    def get_json_from_s3(self, key: str):
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return json.loads(response['Body'].read().decode('utf-8'))
        except NoCredentialsError:
            raise HTTPException(status_code=403, detail="No AWS credentials found")
        except PartialCredentialsError:
            raise HTTPException(status_code=403, detail="Incomplete AWS credentials")
        except ClientError as e:
            raise HTTPException(status_code=e.response['Error']['Code'], detail=e.response['Error']['Message'])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def put_json_to_s3(self, key: str, data: dict):
        try:
            self.s3_client.put_object(Bucket=self.bucket_name, Key=key, Body=json.dumps(data))
        except NoCredentialsError:
            raise HTTPException(status_code=403, detail="No AWS credentials found")
        except PartialCredentialsError:
            raise HTTPException(status_code=403, detail="Incomplete AWS credentials")
        except ClientError as e:
            raise HTTPException(status_code=e.response['Error']['Code'], detail=e.response['Error']['Message'])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def delete_json_from_s3(self, key: str):
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
        except NoCredentialsError:
            raise HTTPException(status_code=403, detail="No AWS credentials found")
        except PartialCredentialsError:
            raise HTTPException(status_code=403, detail="Incomplete AWS credentials")
        except ClientError as e:
            raise HTTPException(status_code=e.response['Error']['Code'], detail=e.response['Error']['Message'])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
