import subprocess
import json
from influxdb_client import InfluxDBClient
from datetime import datetime
import pytz

# InfluxDB连接配置
INFLUXDB_URL = "http://192.168.0.39:30001"
INFLUXDB_TOKEN = "l2yrVMPtDQW6Zl9KEVRI2o3LqloJcZue"
INFLUXDB_ORG = "influxdata"
INFLUXDB_BUCKET_PERFORMANCE = "o1_performance"

client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)

# 将 UTC 时间转换为台湾时间
def convert_to_taiwan_time(utc_time):
    if isinstance(utc_time, str):  # 如果时间是字符串类型
        utc_time = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
    taiwan_tz = pytz.timezone('Asia/Taipei')
    taiwan_time = utc_time.astimezone(taiwan_tz)
    return taiwan_time.strftime("%Y-%m-%d %H:%M:%S")

# 从InfluxDB获取最新RU设备数据
def get_latest_device_data(device_name, bucket_name, measurement_filter=None):
    try:
        query_api = client.query_api()
        measurement_filter = measurement_filter or f'r._measurement == "{device_name}"'
        
        query = f'''
        from(bucket: "{bucket_name}")
          |> range(start: -1h)
          |> filter(fn: (r) => {measurement_filter})
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
        '''

        tables = query_api.query(query)
        device_data = {}
        report_time = None

        for table in tables:
            for record in table.records:
                field = record.get_field()
                value = record.get_value()
                time = record.get_time()
                taiwan_time = convert_to_taiwan_time(time)
                device_data[field] = value
                report_time = taiwan_time

        if report_time:
            device_data['ReportTime'] = report_time
        else:
            print("Error: No valid report_time found from InfluxDB")

        return device_data if device_data else None
    except Exception as e:
        return {"error": str(e)}

# 格式化RU设备响应
def format_ru_response(device_data):
    return {
        "ReportTime": device_data.get("ReportTime", ""),  # 确保ReportTime存在
        "TxAttenuation": float(device_data.get("TxAttenuation", 0))  # 确保是数值型
    }

# 使用curl命令发送RU设备数据
def post_ru_data_with_curl():
    device_name = "RU01001"  # 假设设备名称
    device_data = get_latest_device_data(device_name, INFLUXDB_BUCKET_PERFORMANCE)
    
    if not device_data:
        print("Error: No device data found")
        return

    # 格式化设备数据
    formatted_data = format_ru_response(device_data)

    # 将格式化的数据转为JSON字符串
    data_str = json.dumps(formatted_data)

    # 使用curl命令发送POST请求
    curl_command = f'curl -X POST http://192.168.0.25/api/v1/ORAN/RUData?serverid=10001 -H "Content-Type: application/json" -d \'{data_str}\''
    
    print(f"Executing curl command: {curl_command}")
    
    try:
        # 使用subprocess执行curl命令
        result = subprocess.run(curl_command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # 打印curl命令的输出
        print(result.stdout.decode('utf-8'))
    except subprocess.CalledProcessError as e:
        print(f"Error executing curl command: {e.stderr.decode('utf-8')}")

# 主函数，执行数据发送
if __name__ == "__main__":
    post_ru_data_with_curl()
