from flask import Flask, request, jsonify
from influxdb_client import InfluxDBClient
from datetime import datetime
import pytz
import pymysql
from collections import OrderedDict
import config  # 引入配置文件

app = Flask(__name__)

# InfluxDB连接配置
client = InfluxDBClient(url=config.INFLUXDB_URL, token=config.INFLUXDB_TOKEN, org=config.INFLUXDB_ORG)

# 将 UTC 时间转换为台湾时间
def convert_to_taiwan_time(utc_time):
    if isinstance(utc_time, str):
        utc_time = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
    taiwan_tz = pytz.timezone('Asia/Taipei')
    taiwan_time = utc_time.astimezone(taiwan_tz)
    return taiwan_time.strftime("%Y-%m-%d %H:%M:%S")

# 建立MySQL連線
def get_mysql_connection():
    return pymysql.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_DATABASE,
        cursorclass=pymysql.cursors.DictCursor
    )

# 根據 devicename 從對應的 table 查詢 device_id
def get_device_id_by_name(devicename):
    table_map = {
        "CU": "CUdevicelist",
        "DU": "DUdevicelist",
        "RU": "RUdevicelist",
        "PDU": "PDUdevicelist"
    }
    for prefix, table in table_map.items():
        if devicename.startswith(prefix):
            try:
                connection = get_mysql_connection()
                with connection.cursor() as cursor:
                    sql = f"SELECT deviceid FROM {table} WHERE devicename = %s"
                    cursor.execute(sql, (devicename,))
                    result = cursor.fetchone()
                    return result['deviceid'] if result else 0
            finally:
                connection.close()
    return 0

# 通用函数：从InfluxDB提取最新设备数据
def get_latest_device_data(device_name, bucket_name):
    try:
        query_api = client.query_api()
        query = f'''
        from(bucket: "{bucket_name}")
          |> range(start: -1h)
          |> filter(fn: (r) => r._measurement == "{device_name}")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
        '''

        tables = query_api.query(query)
        device_data = OrderedDict()
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

        return device_data if device_data else None
    except Exception as e:
        return {"error": str(e)}

# 查询CU设备，合并多个bucket
def get_cu_device_data(device_name):
    try:
        query_api = client.query_api()

        performance_query = f'''
        from(bucket: "{config.INFLUXDB_BUCKET_PERFORMANCE}")
          |> range(start: -1h)
          |> filter(fn: (r) => r._measurement == "{device_name}")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
        '''

        pdcp_query = f'''
        from(bucket: "{config.INFLUXDB_BUCKET_PDCP}")
          |> range(start: -1h)
          |> filter(fn: (r) => r._measurement =~ /ue_.+/)
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
        '''

        performance_tables = query_api.query(performance_query)
        pdcp_tables = query_api.query(pdcp_query)

        device_data = OrderedDict()
        report_time = None

        for table in performance_tables:
            for record in table.records:
                device_data[record.get_field()] = record.get_value()
                report_time = convert_to_taiwan_time(record.get_time())

        for table in pdcp_tables:
            for record in table.records:
                device_data[record.get_field()] = record.get_value()

        if report_time:
            device_data['ReportTime'] = report_time

        return device_data if device_data else None
    except Exception as e:
        return {"error": str(e)}

# 轉換回原始資料格式回傳
def format_response(device_type, devicename, device_data):
    result = OrderedDict()
    result["DeviceId"] = get_device_id_by_name(devicename)
    result["DeviceType"] = devicename
    result["ReportTime"] = device_data.pop("ReportTime", "")

    # 特殊格式處理
    if device_type == "PDU":
        result["NumofSocket"] = 4
        result["TotalCurrent"] = device_data.get("inFeedCurrent_index_1", "")
        result["TotalPowerload"] = device_data.get("inFeedPowerLoad_index_1", "")
        result["Socket"] = []
        for i in range(1, 5):
            result["Socket"].append(OrderedDict({
                "SocketId": str(i),
                "SocketVoltage": device_data.get(f"outVoltage_index_{i}", ""),
                "SocketCurrent": device_data.get(f"outCurrent_index_{i}", ""),
                "SocketPowerload": device_data.get(f"outPowerLoad_index_{i}", ""),
                "InFeedPowerEnergy": device_data.get("inFeedPowerEnergy_index_1", "")
            }))
    elif device_type == "CU":
        result["NumofUe"] = int(device_data.get("num_of_ue", 0))
        result["PmData"] = OrderedDict((k, v) for k, v in device_data.items() if not k.startswith("ul_") and not k.startswith("dl_") and not k.startswith("total_"))
        result["TotalUlTp"] = device_data.get("total_ul_tp", "")
        result["TotalUlPkt"] = device_data.get("total_ul_pkt", "")
        result["TotalDlTp"] = device_data.get("total_dl_tp", "")
        result["TotalDlPkt"] = device_data.get("total_dl_pkt", "")
        ue_id = int(device_data.get("ue_id", 0))
        result["Ue"] = [{
            "UeId": ue_id,
            "UlTp": device_data.get("ul_tp", ""),
            "UlPkt": device_data.get("ul_pkt", ""),
            "DlTp": device_data.get("dl_tp", ""),
            "DlPkt": device_data.get("dl_pkt", "")
        }]
    elif device_type == "DU":
        result["PmData"] = OrderedDict((k, v) for k, v in device_data.items())
    else:
        result.update(device_data)

    return result

@app.route('/api/v1/ORAN/deviceList', methods=['GET'])
def get_device_info():
    devicename = request.args.get('Info')
    if not devicename:
        return jsonify({"error": "Device name not provided"}), 400

    bucket_map = {
        "PDU": config.INFLUXDB_BUCKET_SOCKET,
        "RU": config.INFLUXDB_BUCKET_PERFORMANCE,
        "DU": config.INFLUXDB_BUCKET_PERFORMANCE,
        "CU": None
    }

    for dtype, bucket in bucket_map.items():
        if devicename.startswith(dtype):
            if dtype == "CU":
                device_data = get_cu_device_data(devicename)
            else:
                device_data = get_latest_device_data(devicename, bucket)
            device_type = dtype
            break
    else:
        return jsonify({"error": "Unsupported device type"}), 400

    if not device_data:
        return jsonify({"error": "Device data not found"}), 404

    response_data = format_response(device_type, devicename, device_data)
    return jsonify(response_data), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
