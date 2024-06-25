from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()

import time
from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Tuple
import uuid
from s3_utils import S3Utils
from models import Conversation, Block, PartialBlock, PartialConversation, PartialResponse, Response
import os
from cachetools import TTLCache, cached

bucket_name = os.getenv("BUCKET_NAME")
bucket_base_folder = os.getenv("BUCKET_BASE_FOLDER_NAME")
conversations_dir_name = os.getenv("CONVERSATIONS_DIR_NAME")
blocks_dir_name = os.getenv("BLOCKS_DIR_NAME")
responses_dir_name = os.getenv("RESPONSES_DIR_NAME")

# Ensure all required environment variables are set
if not all([bucket_name, bucket_base_folder, conversations_dir_name, blocks_dir_name, responses_dir_name]):
    raise ValueError("One or more required environment variables are missing.")

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

s3_utils = S3Utils(bucket_name=bucket_name)

default_conversation_fields = ['id', 'createdBy', 'createdAt', 'updatedAt', 'status', 'summaryText', 'summaryType', 'blockIds']
default_block_fields = ['id', 'inputText', 'responseIds', 'createdBy', 'createdAt']
default_response_fields = ['id', 'source', 'responseType', 'requestedAt']

# Create a TTL cache with a maximum size of 100 items and a time-to-live of 300 seconds (5 minutes)
cache = TTLCache(maxsize=2048, ttl=300000)

def get_s3_key(conversation_id, block_id=None, response_id=None):
    if response_id:
        return f"{bucket_base_folder}/{conversations_dir_name}/{conversation_id}/{blocks_dir_name}/{block_id}/{responses_dir_name}/{response_id}.json"
    if block_id:
        return f"{bucket_base_folder}/{conversations_dir_name}/{conversation_id}/{blocks_dir_name}/{block_id}.json"
    return f"{bucket_base_folder}/{conversations_dir_name}/{conversation_id}.json"

def filter_nested_fields(data, default_fields, additional_fields=None):
    if not additional_fields:
        additional_fields = []

    # Create a set of fields to include
    include_fields = set(default_fields)
    additional_fields_set = set(additional_fields)

    # Ensure all default fields for nested entities are included
    nested_default_fields = {
        'blocks': default_block_fields,
        'responses': default_response_fields,
    }

    for field in additional_fields_set:
        parts = field.split('.')
        if parts[0] in nested_default_fields:
            include_fields.update(nested_default_fields[parts[0]])

    # Split nested fields into parts
    field_parts = {}
    for field in include_fields | additional_fields_set:
        parts = field.split('.')
        if parts[0] not in field_parts:
            field_parts[parts[0]] = []
        if len(parts) > 1:
            field_parts[parts[0]].append('.'.join(parts[1:]))

    # Filter the fields recursively
    filtered_data = {}
    for key, nested_fields in field_parts.items():
        if key in data:
            value = data[key]
            if nested_fields:
                if isinstance(value, list):
                    filtered_data[key] = [filter_nested_fields(item, nested_default_fields.get(key, []), nested_fields) for item in value]
                else:
                    filtered_data[key] = filter_nested_fields(value, nested_default_fields.get(key, []), nested_fields)
            else:
                filtered_data[key] = value

    return filtered_data

def hash_key(*args, **kwargs):
    return (tuple(args), tuple(sorted(kwargs.items())))

@cached(cache, key=hash_key)
def fetch_blocks(conversation_id: str, block_ids: Tuple[str, ...], fields: str = ''):
    blocks = []
    for block_id in block_ids:
        blocks.append(fetch_block(conversation_id, block_id, fields))
    return blocks

@cached(cache, key=hash_key)
def fetch_block(conversation_id: str, block_id: str, fields: str = ''):
    key = get_s3_key(conversation_id, block_id)
    block = s3_utils.get_json_from_s3(key)
    if fields and ("blocks.responses" in fields or any(field.startswith("blocks.responses.") for field in fields.split(','))):
        block['responses'] = fetch_responses(conversation_id, block_id, tuple(block.get('responseIds', [])))
    return block

@cached(cache, key=hash_key)
def fetch_responses(conversation_id: str, block_id: str, response_ids: Tuple[str, ...]):
    responses = []
    for response_id in response_ids:
        key = get_s3_key(conversation_id, block_id, response_id)
        response = s3_utils.get_json_from_s3(key)
        responses.append(response)
    return responses

# CRUD operations for Conversation
@app.post("/conversation", response_model=Conversation)
def create_conversation(query: str, partial_conversation: PartialConversation = Body(...)):
    try:
        epoch_time = int(time.time())
        conversation_data = {
            'id': str(uuid.uuid4()),
            'status': 'OPEN',
            'summaryText': query,
            'summaryType': 'UNKNOWN',
            'createdAt': epoch_time,
            'updatedAt': epoch_time,
            'blockIds': [],
        }

        conversation_data.update(partial_conversation.dict(exclude_unset=True))
        conversation = Conversation(**conversation_data)

        new_block = Block(
            id=str(uuid.uuid4()),
            inputText=query,
            responseIds=[],
            createdAt=epoch_time,
            createdBy=conversation.createdBy
        )

        conversation.blockIds.append(new_block.id)

        key = get_s3_key(conversation.id)
        s3_utils.put_json_to_s3(key, conversation.dict())

        key = get_s3_key(conversation.id, new_block.id)
        s3_utils.put_json_to_s3(key, new_block.dict())

        return conversation
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversation/{conversation_id}", response_model=Conversation, response_model_exclude_none=True)
def read_conversation(conversation_id: str, fields: Optional[str] = Query(None)):
    try:
        key = get_s3_key(conversation_id)
        conversation = s3_utils.get_json_from_s3(key)

        if fields and ("blocks" in fields or any(field.startswith("blocks.") for field in fields.split(','))):
            conversation['blocks'] = fetch_blocks(conversation_id, tuple(conversation.get('blockIds', [])), fields)

        filtered_conversation = filter_nested_fields(conversation, default_conversation_fields, fields.split(',') if fields else [])
        return filtered_conversation
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/conversation/{conversation_id}", response_model=Conversation)
def update_conversation(conversation_id: str, conversation: Conversation):
    key = get_s3_key(conversation_id)
    s3_utils.put_json_to_s3(key, conversation.dict())
    return conversation

@app.delete("/conversation/{conversation_id}")
def delete_conversation(conversation_id: str):
    key = get_s3_key(conversation_id)
    s3_utils.delete_json_from_s3(key)
    return {"message": "Conversation deleted"}

@app.get("/conversation", response_model=List[Conversation], response_model_exclude_none=True)
def list_conversations(fields: Optional[str] = Query(None)):
    conversations = []
    try:
        response = s3_utils.s3_client.list_objects_v2(Bucket=s3_utils.bucket_name, Prefix=f"{bucket_base_folder}/{conversations_dir_name}/")
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']

                if key.endswith(".json") and key.removeprefix(f"{bucket_base_folder}/{conversations_dir_name}/").count('/') == 0:  # Ensure it's a conversation JSON and not a block or response JSON
                    conversation = s3_utils.get_json_from_s3(key)
                    conversation['blocks'] = fetch_blocks(conversation['id'], tuple(conversation.get('blockIds', [])))

                    filtered_conversation = filter_nested_fields(conversation, default_conversation_fields, fields.split(',') if fields else [])
                    conversations.append(filtered_conversation)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

    return conversations

# CRUD operations for Block
@app.post("/conversation/{conversation_id}/block/", response_model=Block)
def create_block(conversation_id: str, partial_block: PartialBlock = Body(...)):
    epoch_time = int(time.time())
    block_data = {
        'id': str(uuid.uuid4()),
        'createdAt': epoch_time,
        'responseIds': [],
        'createdBy': partial_block.createdBy or {
            'id': 'himanshu@bruviti_com',
            'email': 'himanshu@bruviti.com',
            'displayName': 'Himanshu'
        }
    }
    block_data.update(partial_block.dict(exclude_unset=True))
    block = Block(**block_data)

    key = get_s3_key(conversation_id, block.id)
    s3_utils.put_json_to_s3(key, block.dict())

    key = get_s3_key(conversation_id)
    conversation = s3_utils.get_json_from_s3(key)
    conversation['blockIds'] = conversation['blockIds'] or []
    conversation['blockIds'].append(block.id)
    s3_utils.put_json_to_s3(key, conversation)

    return block

@app.get("/conversation/{conversation_id}/block/{block_id}", response_model=Block, response_model_exclude_none=True)
def read_block(conversation_id: str, block_id: str, fields: Optional[str] = Query(None)):
    key = get_s3_key(conversation_id, block_id)
    block = s3_utils.get_json_from_s3(key)
    block['responses'] = fetch_responses(conversation_id, block_id, tuple(block.get('responseIds', [])))
    filtered_block = filter_nested_fields(block, default_block_fields, fields.split(',') if fields else [])
    return filtered_block

@app.put("/conversation/{conversation_id}/block/{block_id}", response_model=Block)
def update_block(conversation_id: str, block_id: str, block: Block):
    key = get_s3_key(conversation_id, block_id)
    s3_utils.put_json_to_s3(key, block.dict())
    return block

@app.delete("/conversation/{conversation_id}/block/{block_id}")
def delete_block(conversation_id: str, block_id: str):
    key = get_s3_key(conversation_id, block_id)
    s3_utils.delete_json_from_s3(key)
    return {"message": "Block deleted"}

# CRUD operations for Response
@app.post("/conversation/{conversation_id}/block/{block_id}/response/", response_model=Response)
def create_response(conversation_id: str, block_id: str, partial_response: PartialResponse = Body(...)):
    epoch_time = int(time.time())
    response_data = {
        'id': str(uuid.uuid4()),
        'respondedAt': epoch_time,
    }

    if 'respondedAt' not in partial_response.dict():
        response_data['respondedAt'] = epoch_time

    response_data.update(partial_response.dict(exclude_unset=True))
    response = Response(**response_data)

    key = get_s3_key(conversation_id, block_id, response.id)
    s3_utils.put_json_to_s3(key, response.dict())

    block = Block(**fetch_block(conversation_id, block_id, ''))
    block.responseIds.append(response.id)

    key = get_s3_key(conversation_id, block_id)
    s3_utils.put_json_to_s3(key, block.dict())

    return response

@app.get("/conversation/{conversation_id}/block/{block_id}/response/{response_id}", response_model=Response, response_model_exclude_none=True)
def read_response(conversation_id: str, block_id: str, response_id: str, fields: Optional[str] = Query(None)):
    key = get_s3_key(conversation_id, block_id, response_id)
    response = s3_utils.get_json_from_s3(key)
    filtered_response = filter_nested_fields(response, default_response_fields, fields.split(',') if fields else [])
    return filtered_response

@app.put("/conversation/{conversation_id}/block/{block_id}/response/{response_id}", response_model=Response)
def update_response(conversation_id: str, block_id: str, response_id: str, response: Response):
    key = get_s3_key(conversation_id, block_id, response_id)
    s3_utils.put_json_to_s3(key, response.dict())
    return response

@app.delete("/conversation/{conversation_id}/block/{block_id}/response/{response_id}")
def delete_response(conversation_id: str, block_id: str, response_id: str):
    key = get_s3_key(conversation_id, block_id, response_id)
    s3_utils.delete_json_from_s3(key)
    return {"message": "Response deleted"}

# To run the application, use the command: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
