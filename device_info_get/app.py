from flask import Flask, request, jsonify
from influxdb_client import InfluxDBClient
from datetime import datetime
import pytz
from collections import OrderedDict

app = Flask(__name__)

# InfluxDB连接配置
INFLUXDB_URL = "http://192.168.0.39:30001"
INFLUXDB_TOKEN = "l2yrVMPtDQW6Zl9KEVRI2o3LqloJcZue"
INFLUXDB_ORG = "influxdata"
INFLUXDB_BUCKET_PERFORMANCE = "o1_performance"
INFLUXDB_BUCKET_SOCKET = "socket_info"
INFLUXDB_BUCKET_PDCP = "PDCP_Throughput"

client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)

# 将 UTC 时间转换为台湾时间
def convert_to_taiwan_time(utc_time):
    if isinstance(utc_time, str):  # 如果时间是字符串类型
        utc_time = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
    taiwan_tz = pytz.timezone('Asia/Taipei')
    taiwan_time = utc_time.astimezone(taiwan_tz)
    return taiwan_time.strftime("%Y-%m-%d %H:%M:%S")

# 从InfluxDB提取最新设备数据并打印
def get_latest_device_data(device_name, bucket_name):
    query_api = client.query_api()

    query = f'''
    from(bucket: "{bucket_name}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "{device_name}")
      |> sort(columns: ["_time"], desc: true)
      |> limit(n: 1)
    '''

    tables = query_api.query(query)

    device_data = {}
    for table in tables:
        for record in table.records:
            field = record.get_field()
            value = record.get_value()
            time = record.get_time()  # 提取时间字段
            taiwan_time = convert_to_taiwan_time(time)  # 转换为台湾时间
            # 打印提取到的字段、值和时间
            print(f"Field: {field}, Value: {value}, Time (Taiwan): {taiwan_time}")
            device_data[field] = value

    # 将台湾时间也添加到device_data中
    device_data['ReportTime'] = taiwan_time

    return device_data


# 针对CU设备查询两个bucket
def get_cu_device_data(device_name):
    # 从 o1_performance bucket 查询数据
    performance_data = get_latest_device_data(device_name, INFLUXDB_BUCKET_PERFORMANCE)

    # 从 PDCP_Throughput bucket 查询数据
    pdcp_data = get_latest_device_data(device_name, INFLUXDB_BUCKET_PDCP)

    # 合并两个数据源的结果
    combined_data = {**performance_data, **pdcp_data}
    return combined_data

# 根据设备类型返回不同格式的响应
def format_device_response(devicename, device_data):
    if devicename.startswith("RU"):
        # RU 设备格式
        return {
            "ReportTime": device_data.get("ReportTime", ""),
            "TxAttenuation": device_data.get("tx_attenuation", "")
        }
    elif devicename.startswith("DU"):
        # DU 设备格式
        return {
            "DeviceId": device_data.get("DeviceId", ""),
            "DeviceType": devicename,
            "ReportTime": device_data.get("ReportTime", ""),
            "PmData": {
                "RRUPrbTotDl": device_data.get("RRUPrbTotDl", ""),
                "RRUPrbAvailDl": device_data.get("RRUPrbAvailDl", "")
            }
        }
    elif devicename.startswith("CU"):
        # CU 设备格式
        return {
            "DeviceId": device_data.get("DeviceId", ""),
            "DeviceType": devicename,
            "ReportTime": device_data.get("ReportTime", ""),
            "PmData": {
                "PAGReceivedNbrCnInitiated": device_data.get("PAGReceivedNbrCnInitiated", ""),
                "PAGDiscardedNbrCnInitiated": device_data.get("PAGDiscardedNbrCnInitiated", ""),
                # 从PDCP_Throughput bucket中的数据
                "PdcpThroughputDl": device_data.get("PdcpThroughputDl", ""),
                "PdcpThroughputUl": device_data.get("PdcpThroughputUl", "")
            }
        }
    elif devicename.startswith("PDU"):
        # PDU 设备格式
        return OrderedDict({
            "Deviceid": device_data.get("DeviceId", ""),
            "DeviceType": "5001",
            "NumofSocket": 4,
            "TotalCurrent": device_data.get("inFeedCurrent_index_1", ""),
            "TotalPowerload": device_data.get("inFeedPowerLoad_index_1", ""),
            "ReportTime": device_data.get("ReportTime", ""),
            "Socket": [
                {
                    "SocketId": "1",
                    "SocketVoltage": device_data.get("outVoltage_index_1", ""),
                    "SocketCurrent": device_data.get("outCurrent_index_1", ""),
                    "SocketPowerload": device_data.get("outPowerLoad_index_1", ""),
                    "InFeedPowerEnergy": device_data.get("inFeedPowerEnergy_index_1", ""),
                },
                {
                    "SocketId": "2",
                    "SocketVoltage": device_data.get("outVoltage_index_2", ""),
                    "SocketCurrent": device_data.get("outCurrent_index_2", ""),
                    "SocketPowerload": device_data.get("outPowerLoad_index_2", ""),
                    "InFeedPowerEnergy": device_data.get("inFeedPowerEnergy_index_1", ""),
                },
                {
                    "SocketId": "3",
                    "SocketVoltage": device_data.get("outVoltage_index_3", ""),
                    "SocketCurrent": device_data.get("outCurrent_index_3", ""),
                    "SocketPowerload": device_data.get("outPowerLoad_index_3", ""),
                    "InFeedPowerEnergy": device_data.get("inFeedPowerEnergy_index_1", ""),
                },
                {
                    "SocketId": "4",
                    "SocketVoltage": device_data.get("outVoltage_index_4", ""),
                    "SocketCurrent": device_data.get("outCurrent_index_4", ""),
                    "SocketPowerload": device_data.get("outPowerLoad_index_4", ""),
                    "InFeedPowerEnergy": device_data.get("inFeedPowerEnergy_index_1", "")
                }
            ]
        })
    else:
        return {"error": "Unknown device type"}

# API 路由
@app.route('/api/v1/ORAN/deviceList', methods=['GET'])
def get_device_info():
    devicename = request.args.get('Info')
    if not devicename:
        return jsonify({"error": "Device name not provided"}), 400

    # 根据设备类型选择相应的bucket
    if devicename.startswith("PDU"):
        bucket_name = INFLUXDB_BUCKET_SOCKET
        device_data = get_latest_device_data(devicename, bucket_name)
    elif devicename.startswith("CU"):
        # CU设备需要查询两个bucket
        device_data = get_cu_device_data(devicename)
    else:
        bucket_name = INFLUXDB_BUCKET_PERFORMANCE
        device_data = get_latest_device_data(devicename, bucket_name)

    if not device_data:
        return jsonify({"error": "Device data not found"}), 404

    # 格式化响应
    response = format_device_response(devicename, device_data)

    return jsonify(response), 200

# 主函数
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
