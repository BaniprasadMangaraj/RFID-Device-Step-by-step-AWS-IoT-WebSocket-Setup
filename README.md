# AWS IoT to WebSocket Setup for RFID-Device-01

This guide shows how to set up RFID-Device-01 to send data to AWS IoT, forward messages to Lambda, and push updates to browser clients using API Gateway WebSocket.

## Architecture Overview
- RFID Device → AWS IoT Core → IoT Rule → Lambda → API Gateway WebSocket → Browser Dashboard

  <img width="1260" height="599" alt="image" src="https://github.com/user-attachments/assets/d9a796bb-8daa-4b67-a7e7-129f65ad6e00" />

  <img width="1249" height="628" alt="image" src="https://github.com/user-attachments/assets/173314b1-f78f-46d4-a61a-74edabbba4bb" />



## Prerequisites
- AWS account with permissions for IoT Core, Lambda, DynamoDB, API Gateway
- Windows PC (paths use `D:\IOTCoreCert\`)
- MQTT client on device (mosquitto_pub or MQTT library)
- Text editor for code files

## Step 1: Create IoT Thing and Certificates

### Create Thing
1. Go to AWS Console → IoT Core → Manage → Things
2. Click **Create thing** → **Create a single thing**
3. Enter Thing name: `RFID-Device-01` → **Create**

### Download Certificates
When prompted, create and download:
- `certificatePem` (device certificate)
- `keyPair.privateKey` (device private key)
- `AmazonRootCA1.pem` (root CA)

Save to: `D:\IOTCoreCert\`

### Create and Attach Policy
1. IoT Core → Secure → Policies → **Create policy**
2. Example policy actions:
   ```json
   {
     "Effect": "Allow",
     "Action": [
       "iot:Connect",
       "iot:Publish",
       "iot:Subscribe",
       "iot:Receive"
     ],
     "Resource": "*"
   }
   ```
3. Activate certificate and attach to Thing

## Step 2: Device Configuration

### AWS IoT Core Settings
```python
# AWS IoT Core Configuration
ENDPOINT = "**************-ats.iot.ap-south-1.amazonaws.com"
CLIENT_ID = "RFID-Device-01"
TOPIC = f"smaket/iot/data/{CLIENT_ID}"

# Certificate paths (Windows)
CA_PATH   = r"D:\IOTCoreCert\AmazonRootCA1.pem"
CERT_PATH = r"D:\IOTCoreCert\92ddddd702f846e95f69cfabf5b3b10df7309fab9d85b34bbfa07a763b1df0d1-certificate.pem.crt"
KEY_PATH  = r"D:\IOTCoreCert\92ddddd702f846e95f69cfabf5b3b10df7309fab9d85b34bbfa07a763b1df0d1-private.pem.key"
```

### Test with mosquitto_pub
```bash
"C:\Program Files\mosquitto\mosquitto_pub.exe" \
  --host **************-ats.iot.ap-south-1.amazonaws.com \
  --port 8883 \
  --cafile "D:\IOTCoreCert\AmazonRootCA1.pem" \
  --cert "D:\IOTCoreCert\92dd...-certificate.pem.crt" \
  --key "D:\IOTCoreCert\92dd...-private.pem.key" \
  --id RFID-Device-01 \
  -t "smaket/iot/data/RFID-Device-01" \
  -m "{\"tagId\":\"E2003411\", \"timestamp\":\"2025-10-31T10:00:00Z\"}"
```

## Step 3: Create IoT Rule

1. IoT Core → Act → Rules → **Create rule**
2. Name: `ForwardToLambda`
3. Rule query statement:
   ```sql
   SELECT *, topic() AS mqttTopic FROM 'smaket/iot/data/#'
   ```
4. Add action: **Invoke Lambda** → Select `IoTToWebSocket-Multi`

## Step 4: Create Lambda Functions

### IoTToWebSocket-Multi Lambda
**Runtime:** Python 3.9+

**Required IAM Permissions:**
- `dynamodb:Scan`, `dynamodb:DeleteItem`
- `execute-api:ManageConnections`

**Code:**
```python
import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('WebSocketConnections-Multi')

apigw = boto3.client(
    'apigatewaymanagementapi',
    endpoint_url='https://**********.execute-api.ap-south-1.amazonaws.com/prod_multi/'
)

def lambda_handler(event, context):
    print("Incoming IoT Event:")
    print(json.dumps(event))

    mqtt_topic = event.get('mqttTopic', '')
    device_id = mqtt_topic.split('/')[-1] if mqtt_topic else None

    if not device_id:
        return {'statusCode': 400, 'body': 'No device_id in topic'}

    message = json.dumps(event)

    # Get connections
    try:
        response = table.scan()
        connections = response.get('Items', [])
    except Exception as e:
        print('DynamoDB scan failed:', e)
        return {'statusCode': 500}

    for item in connections:
        connection_id = item['connectionId']
        subscribed_devices = item.get('subscribed_devices', [])

        if device_id in subscribed_devices:
            try:
                apigw.post_to_connection(ConnectionId=connection_id, Data=message.encode('utf-8'))
            except apigw.exceptions.GoneException:
                table.delete_item(Key={'connectionId': connection_id})
            except Exception as e:
                print('Post to connection failed:', e)

    return {'statusCode': 200}
```

## Step 5: Create DynamoDB Table

**Table name:** `WebSocketConnections-Multi`
**Primary key:** `connectionId` (String)

Example item:
```json
{
  "connectionId": "abc123",
  "subscribed_devices": ["RFID-Device-01"]
}
```

## Step 6: WebSocket API Gateway

### Create WebSocket API
1. API Gateway → **WebSocket API** → **Build**
2. Name: `IoT-WebSocket-API-Multi`
3. Route selection expression: `$request.body.action`

### Configure Routes
- `$connect` → `WSConnect-Multi` Lambda
- `$disconnect` → `WSDisconnect-Multi` Lambda
- `subscribeDevice` → `subscribeDevice` Lambda

### Deploy API
- Stage: `prod_multi`
- WebSocket URL: `wss://**********.execute-api.ap-south-1.amazonaws.com/prod_multi/`

## Step 7: WebSocket Lambda Functions

### WSConnect-Multi Lambda
```python
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('WebSocketConnections-Multi')

def lambda_handler(event, context):
    connection_id = event['requestContext']['connectionId']
    table.put_item(Item={"connectionId": connection_id, "subscribed_devices": []})
    return {"statusCode": 200, "body": "Connected."}
```

### WSDisconnect-Multi Lambda
```python
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('WebSocketConnections-Multi')

def lambda_handler(event, context):
    connection_id = event['requestContext']['connectionId']
    table.delete_item(Key={'connectionId': connection_id})
    return {'statusCode': 200, 'body': 'Disconnected.'}
```

### subscribeDevice Lambda
```python
import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('WebSocketConnections-Multi')

def lambda_handler(event, context):
    connection_id = event['requestContext']['connectionId']

    try:
        body = json.loads(event.get('body') or '{}')
        device_id = body.get('device_id')
    except Exception:
        return {'statusCode': 400, 'body': 'Invalid JSON'}

    if not device_id:
        return {'statusCode': 400, 'body': 'Missing device_id'}

    table.update_item(
        Key={'connectionId': connection_id},
        UpdateExpression="SET subscribed_devices = list_append(if_not_exists(subscribed_devices, :empty), :d)",
        ExpressionAttributeValues={':d': [device_id], ':empty': []}
    )

    return {'statusCode': 200, 'body': f'Subscribed to {device_id}'}
```

## Step 8: Dashboard HTML

Create `dashboard.html`:

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>RFID Dashboard</title>
  <style>
    body{font-family:Arial;padding:20px}
    #log{white-space:pre-wrap;border:1px solid #ccc;padding:10px;height:300px;overflow:auto}
  </style>
</head>
<body>
  <h2>RFID Dashboard</h2>
  <label>Device ID: <input id="deviceId" value="RFID-Device-01"></label>
  <button id="connect">Connect & Subscribe</button>
  <div id="status">Disconnected</div>
  <div id="log"></div>

  <script>
    const WS_URL = "wss://**********.execute-api.ap-south-1.amazonaws.com/prod_multi/";
    let ws;
    document.getElementById('connect').onclick = () => {
      const deviceId = document.getElementById('deviceId').value;
      ws = new WebSocket(WS_URL);
      ws.onopen = () => {
        document.getElementById('status').innerText = 'Connected';
        // send subscribe action
        ws.send(JSON.stringify({action: 'subscribeDevice', device_id: deviceId}));
      };
      ws.onmessage = (evt) => {
        document.getElementById('log').innerText += '\n' + evt.data;
      };
      ws.onclose = () => { document.getElementById('status').innerText = 'Disconnected'; };
    };
  </script>
</body>
</html>
```

## Testing

1. Run mosquitto_pub command to send test message
2. Check CloudWatch logs for IoTToWebSocket-Multi Lambda
3. Open dashboard.html and click **Connect**
4. You should receive messages when device publishes

## Troubleshooting

- **No messages in Lambda logs**: Check IoT Rule is enabled and Lambda is attached
- **WebSocket connects but no messages**: Verify API Gateway endpoint URL in Lambda
- **TLS errors**: Check certificate paths and activation status
- **DynamoDB errors**: Verify table name and Lambda permissions

## Security Notes

- Use least privilege in IAM policies
- Limit IoT policy to required topics only
- Rotate certificates if compromised

## Final Checklist

- [ ] Thing created with certificates downloaded
- [ ] Certificates copied to `D:\IOTCoreCert\`
- [ ] Device configured and test mosquitto_pub works
- [ ] IoT Rule `ForwardToLambda` created and enabled
- [ ] Lambda `IoTToWebSocket-Multi` created with correct endpoint
- [ ] DynamoDB table `WebSocketConnections-Multi` created
- [ ] API Gateway WebSocket deployed to `prod_multi`
- [ ] dashboard.html tested and receiving messages
