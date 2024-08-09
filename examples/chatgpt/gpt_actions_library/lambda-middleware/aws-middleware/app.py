import json

def lambda_handler(event, context):
    # Return success response
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': json.dumps({'success': True})
    }
