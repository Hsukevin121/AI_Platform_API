from flask import Flask, request, jsonify
import xml.etree.ElementTree as ET
import json
import requests
from ncclient import manager
import config  # 引用配置文件
from functools import wraps
import base64
import time

app = Flask(__name__)

# 用户名和密码
USERNAME = 'AIadmin'
PASSWORD = 'admin0000'

# 验证装饰器
def authenticate(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if auth_header:
            auth_type, credentials = auth_header.split(' ')
            if auth_type.lower() == 'basic':
                decoded_credentials = base64.b64decode(credentials).decode('utf-8')
                username, password = decoded_credentials.split(':')
                if username == USERNAME and password == PASSWORD:
                    return func(*args, **kwargs)
        return jsonify({'status': '401', 'msg': 'Unauthorized'}), 400
    return decorated_function

# Function to execute NETCONF command and parse data
def get_bbu_info():
    try:
        with manager.connect(**config.device_params, hostkey_verify=False) as m:
            print("NETCONF Session Connected Successfully.")
            get_reply = m.get(filter=('subtree', config.filter_str))
            print("NETCONF GET Operation Result:")
            print(get_reply)

            # Parse the XML data
            root = ET.fromstring(str(get_reply))
            namespaces = {
                'base': 'urn:ietf:params:xml:ns:netconf:base:1.0',
                'multiran': 'urn:reign-altran-o1-cm-multiran:1.0'
            }

            # Find all ran-id elements and their corresponding data
            ran_data = {}
            for multiran_cm in root.findall('.//multiran:multiran-cm', namespaces):
                ran_id = multiran_cm.find('multiran:ran-id', namespaces).text
                PLMNID = multiran_cm.find('.//multiran:PLMNID', namespaces).text
                BBU_IP = multiran_cm.find('.//multiran:IP_info/multiran:BBU_IP', namespaces).text
                BBU_NETMASK = multiran_cm.find('.//multiran:IP_info/multiran:BBU_NETMASK', namespaces).text
                BBU_Gateway_IP = multiran_cm.find('.//multiran:IP_info/multiran:BBU_Gateway_IP', namespaces).text
                AMF_IP = multiran_cm.find('.//multiran:IP_info/multiran:AMF_IP', namespaces).text
                gNB_ID = multiran_cm.find('.//multiran:NCI/multiran:gNB_ID', namespaces).text

                ran_data[ran_id] = {
                    "PLMNID": PLMNID,
                    "BBU_IP": BBU_IP,
                    "BBU_NETMASK": BBU_NETMASK,
                    "BBU_Gateway_IP": BBU_Gateway_IP,
                    "AMF_IP": AMF_IP,
                    "gNB_ID": gNB_ID
                }

            return ran_data
    except Exception as e:
        print(f"Failed to retrieve BBU Info: {e}")
        return None

# Function to send data to VES Collector
def send_to_ves_collector(ran_id, ran_info):
    payload = {
        "event": {
            "commonEventHeader": {
                "domain": "other",
                "eventId": "node1.cluster.local_2024-04-19T08:51:36.801439+00:00Z",
                "eventName": "heartbeat_O_RAN_COMPONENT",
                "eventType": "O_RAN_COMPONENT",
                "lastEpochMicrosec": 1713516696801439,
                "nfNamingCode": "SDN-Controller",
                "nfVendorName": "O-RAN-SC OAM",
                "priority": "Low",
                "reportingEntityId": "",
                "reportingEntityName": "node1.cluster.local",
                "sequence": 357,
                "sourceId": "",
                "sourceName": "node1.cluster.local",
                "startEpochMicrosec": 1713516696801439,
                "timeZoneOffset": "+00:00",
                "version": "4.1",
                "vesEventListenerVersion": "7.2.1"
            },
            "otherFields": {
                "otherFieldsVersion": "3.0",
                "arrayOfNamedHashMap": [
                    {
                        "name": ran_id,
                        "hashMap": ran_info
                    }
                ]
            }
        }
    }

    payload_json = json.dumps(payload, indent=2)
    headers = {"Content-Type": "application/json"}

    try:
        print(f"Sending data to VES Collector: {payload_json}")
        response = requests.post(config.VES_COLLECTOR_URL, headers=headers, data=payload_json, auth=(config.VES_COLLECTOR_USERNAME, config.VES_COLLECTOR_PASSWORD), verify=False)
        print(f"VES Collector Response status code: {response.status_code}")
        print(f"VES Collector Response text: {response.text}")
        return response.status_code == 202
    except Exception as e:
        print(f"Failed to send data to VES Collector: {e}")
        return False

# Function to check if data exists in InfluxDB 2.0
def check_influxdb(ran_id):
    time.sleep(5)
    query = f'from(bucket: "{config.INFLUXDB_BUCKET}") |> range(start: -30s) |> filter(fn: (r) => r._measurement == "BBU_Info" and r.name == "{ran_id}")'
    headers = {
        "Authorization": f"Token {config.INFLUXDB_TOKEN}",
        "Content-Type": "application/vnd.flux"
    }
    url = f"{config.INFLUXDB_URL}/api/v2/query"
    params = {
        "org": config.INFLUXDB_ORG
    }

    try:
        print(f"Sending query to InfluxDB: {query}")
        response = requests.post(url, headers=headers, params=params, data=query)
        print(f"Response status code: {response.status_code}")
        print(f"Response text: {response.text}")

        if response.status_code == 200:
            if response.text.strip() == "":
                print("InfluxDB query response is empty")
                return False
            else:
                print(f"InfluxDB query response: {response.text}")
                return True
        return False
    except Exception as e:
        print(f"Failed to query InfluxDB: {e}")
        return False

@app.route('/api/v1/ORAN/quick_check', methods=['GET'])
@authenticate
def quick_check():
    ran_data = get_bbu_info()
    if not ran_data:
        return jsonify({"status": "error", "message": "Failed to retrieve BBU Info from NETCONF"}), 402

    for ran_id, ran_info in ran_data.items():
        if not send_to_ves_collector(ran_id, ran_info):
            return jsonify({"status": "error", "message": f"Failed to send data to VES Collector for {ran_id}"}), 403

        if not check_influxdb(ran_id):
            return jsonify({"status": "error", "message": f"Data not found in InfluxDB for {ran_id}"}), 404

    return jsonify({"status": "success", "message": "Quick check passed, all data correctly stored in InfluxDB"}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080 )
