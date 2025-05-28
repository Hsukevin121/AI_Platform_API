import requests
from flask import Flask, jsonify
from influxdb_client import InfluxDBClient
from datetime import datetime
import pytz
from collections import OrderedDict
import threading
import pymysql

app = Flask(__name__)

# InfluxDB连接配置
INFLUXDB_URL = "http://192.168.0.39:30001"
INFLUXDB_TOKEN = "bzgBwlyDG8ZWBo0LP2hpbJ48I9zhZtMR"
INFLUXDB_ORG = "influxdata"
INFLUXDB_BUCKET_PERFORMANCE = "o1_performance"
INFLUXDB_BUCKET_SOCKET = "socket_info"
INFLUXDB_BUCKET_PDCP = "PDCP_Throughput"

client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)

# 将 UTC 时间转换为台湾时间
def convert_to_taiwan_time(utc_time):
    if isinstance(utc_time, str):
        utc_time = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
    taiwan_tz = pytz.timezone('Asia/Taipei')
    taiwan_time = utc_time.astimezone(taiwan_tz)
    return taiwan_time.strftime("%Y-%m-%d %H:%M:%S")

# 從 MySQL 擷取所有裝置資訊
def fetch_device_names_from_db():
    connection = pymysql.connect(
        host='192.168.0.39',
        user='root',
        password='ubuntu',
        database='devicelist'
    )
    device_list = []
    try:
        with connection.cursor() as cursor:
            table_map = {
                'RU': 'RUdevicelist',
                'DU': 'DUdevicelist',
                'CU': 'CUdevicelist',
                'PDU': 'PDUdevicelist'
            }
            for device_type, table in table_map.items():
                cursor.execute(f"SELECT devicename, deviceid FROM {table}")
                for name, deviceid in cursor.fetchall():
                    device_list.append({"name": name, "type": device_type, "deviceid": deviceid})
    finally:
        connection.close()
    return device_list

# 查詢 InfluxDB 單一 bucket 最新資料
def get_latest_device_data(device_name, bucket_name):
    try:
        query_api = client.query_api()
        query = f'''
        from(bucket: "{bucket_name}")
          |> range(start: -5m)
          |> filter(fn: (r) => r._measurement == "{device_name}")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
        '''
        tables = query_api.query(query)
        data, report_time = {}, None
        for table in tables:
            for record in table.records:
                data[record.get_field()] = str(record.get_value())
                report_time = convert_to_taiwan_time(record.get_time())
        if report_time:
            data['ReportTime'] = report_time
        return data if data else None
    except Exception as e:
        return {"error": str(e)}

# 查詢 CU 特殊邏輯 (兩個 bucket)
def get_cu_device_data(device_name):
    try:
        query_api = client.query_api()
        device_data = {}
        report_time = None

        performance_query = f'''
        from(bucket: "{INFLUXDB_BUCKET_PERFORMANCE}")
          |> range(start: -5m)
          |> filter(fn: (r) => r._measurement == "{device_name}")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
        '''
        pdcp_query = f'''
        from(bucket: "{INFLUXDB_BUCKET_PDCP}")
          |> range(start: -5m)
          |> filter(fn: (r) => r._measurement == "ue_sum_info" or r._measurement == "ue_info")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
        '''
        performance_tables = query_api.query(performance_query)
        pdcp_tables = query_api.query(pdcp_query)

        for table in performance_tables:
            for record in table.records:
                device_data[record.get_field()] = str(record.get_value())
                report_time = convert_to_taiwan_time(record.get_time())

        for table in pdcp_tables:
            for record in table.records:
                device_data[record.get_field()] = str(record.get_value())

        if report_time:
            device_data['ReportTime'] = report_time
        return device_data if device_data else None
    except Exception as e:
        return {"error": str(e)}

# 封裝格式化資料
def format_response(device_type, device_data, deviceid, devicename):
    base = OrderedDict({
        "DeviceId": deviceid,
        "DeviceType": devicename,
        "ReportTime": device_data.get("ReportTime", "")
    })

    if device_type == 'RU':
        base["TxAttenuation"] = device_data.get("tx_attenuation", "")

    elif device_type == 'PDU':
        base.update({
            "NumofSocket": 4,
            "TotalCurrent": float(device_data.get("inFeedCurrent_index_1", 0)),
            "TotalPowerload": int(float(device_data.get("inFeedPowerLoad_index_1", 0))),
            "Socket": [
                {
                    "SocketId": i,
                    "SocketVoltage": float(device_data.get(f"outVoltage_index_{i+1}", 0)),
                    "SocketCurrent": float(device_data.get(f"outCurrent_index_{i+1}", 0)),
                    "SocketPowerload": float(device_data.get(f"outPowerLoad_index_{i+1}", 0)),
                    "InFeedPowerEnergy": float(device_data.get("inFeedPowerEnergy_index_1", 0))
                } for i in range(4)
            ]
        })


    elif device_type == 'CU':
        ue_list = []
        num_of_ue = int(device_data.get("num_of_ue", 0))
        for ue_id in range(num_of_ue):
            ue_list.append({
                "UeId": ue_id,
                "UlTp": device_data.get("ul_tp", ""),
                "UlPkt": device_data.get("ul_pkt", ""),
                "DlTp": device_data.get("dl_tp", ""),
                "DlPkt": device_data.get("dl_pkt", "")
            })
        base.update({
            "PmData": {"PAGReceivedNbrCnInitiated": device_data.get("PAG.ReceivedNbrCnInitiated", ""),
                "PAGDiscardedNbrCnInitiated": device_data.get("PAG.DiscardedNbrCnInitiated", ""),
                "MMHoPrepInterReq": device_data.get("MM.HoPrepInterReq", ""),
                "MMHoResAlloInterReq": device_data.get("MM.HoResAlloInterReq", ""),
                "MMHoExeInterReq": device_data.get("MM.HoExeInterReq", ""),
                "MMHoPrepInterSucc": device_data.get("MM.HoPrepInterSucc", ""),
                "MMHoResAlloInterSucc": device_data.get("MM.HoResAlloInterSucc", ""),
                "MMHoExeInterSucc": device_data.get("MM.HoExeInterSucc", ""),
                "MMHoPrepInterFail": device_data.get("MM.HoPrepInterFail", ""),
                "MMHoResAlloInterFail": device_data.get("MM.HoResAlloInterFail", ""),
                "MMMM.HoExeInterFail.UeCtxtRelCmd.cause": device_data.get("MM.MM.HoExeInterFail.UeCtxtRelCmd.cause", ""),
                "MMHoPrepIntraReq": device_data.get("MM.HoPrepIntraReq", ""),
                "MMHoExeIntraReq": device_data.get("MM.HoExeIntraReq", ""),
                "MMHoPrepIntraSucc": device_data.get("MM.HoPrepIntraSucc", ""),
                "MMHoExeIntraSucc": device_data.get("MM.HoExeIntraSucc", ""),
                "RRCConnMean": device_data.get("RRC.ConnMean", ""),
                "RRCConnMax": device_data.get("RRC.ConnMax", ""),
                "RRCConnEstabAtt": device_data.get("RRC.ConnEstabAtt", ""),
                "RRCConnEstabSucc": device_data.get("RRC.ConnEstabSucc", ""),
                "RRCReEstabAtt": device_data.get("RRC.ReEstabAtt", ""),
                "RRCReEstabSuccWithUeContext": device_data.get("RRC.ReEstabSuccWithUeContext", ""),
                "RRCReEstabSuccWithoutUeContext": device_data.get("RRC.ReEstabSuccWithoutUeContext", ""),
                "PAGSuccessRatio": device_data.get("PAG.SuccessRatio", ""),
                "QosFlowPdcpPduVolumeDl": device_data.get("QosFlow.PdcpPduVolumeDl_QCI.9", ""),
                "QosFlowPdcpPduVolumeUl": device_data.get("QosFlow.PdcpPduVolumeUl_QCI.9", ""),
                "SysDataVolumeDL": device_data.get("Sys.DataVolumeDL", ""),
                "SysDataVolumeUL": device_data.get("Sys.DataVolumeUL", ""),
                "SysSpecEffDL": device_data.get("Sys.SpecEffDL", ""),
                "SysSpecEffUL": device_data.get("Sys.SpecEffUL", ""),
                "SysCellAvail": device_data.get("Sys.CellAvail", "")},
            "NumofUe": num_of_ue,
            "TotalUlTp": str(device_data.get("total_ul_tp", "")),
            "TotalUlPkt": str(device_data.get("total_ul_pkt", "")),
            "TotalDlTp": str(device_data.get("total_dl_tp", "")),
            "TotalDlPkt": str(device_data.get("total_dl_pkt", "")),
            "Ue": ue_list
        })

    elif device_type == 'DU':
        base.update({
            "PmData": {"RRUPrbTotDl": device_data.get("RRU.PrbTotDl", ""),
            "RRUPrbAvailDl": device_data.get("RRU.PrbAvailDl", ""),
            "RRUPrbTotUl": device_data.get("RRU.PrbTotUl", ""),
            "RRUPrbAvailUl": device_data.get("RRU.PrbAvailUl", ""),
            "RRUPrbTotDlDistBinBelow50Percentage": device_data.get("RRU.PrbTotDlDist.BinBelow50Percentage", ""),
            "RRUPrbTotDlDistBin50To60Percentage": device_data.get("RRU.PrbTotDlDist.Bin50To60Percentage", ""),
            "RRUPrbTotDlDistBin61To70Percentage": device_data.get("RRU.PrbTotDlDist.Bin61To70Percentage", ""),
            "RRUPrbTotDlDistBin71To80Percentage": device_data.get("RRU.PrbTotDlDist.Bin71To80Percentage", ""),
            "RRUPrbTotDlDistBin81To85Percentage": device_data.get("RRU.PrbTotDlDist.Bin81To85Percentage", ""),
            "RRUPrbTotDlDistBin86To90Percentage": device_data.get("RRU.PrbTotDlDist.Bin86To90Percentage", ""),
            "RRUPrbTotDlDistBin91To93Percentage": device_data.get("RRU.PrbTotDlDist.Bin91To93Percentage", ""),
            "RRUPrbTotDlDistBin94To96Percentage": device_data.get("RRU.PrbTotDlDist.Bin94To96Percentage", ""),
            "RRUPrbTotDlDistBin97To98Percentage": device_data.get("RRU.PrbTotDlDist.Bin97To98Percentage", ""),
            "RRUPrbTotDlDistBinAbove98Percentage": device_data.get("RRU.PrbTotDlDist.BinAbove98Percentage", ""),
            "RRUPrbTotUlDistBinBelow50Percentage": device_data.get("RRU.PrbTotUlDist.BinBelow50Percentage", ""),
            "RRUPrbTotUlDistBin50To60Percentage": device_data.get("RRU.PrbTotUlDist.Bin50To60Percentage", ""),
            "RRUPrbTotUlDistBin61To70Percentage": device_data.get("RRU.PrbTotUlDist.Bin61To70Percentage", ""),
            "RRUPrbTotUlDistBin71To80Percentage": device_data.get("RRU.PrbTotUlDist.Bin71To80Percentage", ""),
            "RRUPrbTotUlDistBin81To85Percentage": device_data.get("RRU.PrbTotUlDist.Bin81To85Percentage", ""),
            "RRUPrbTotUlDistBin86To90Percentage": device_data.get("RRU.PrbTotUlDist.Bin86To90Percentage", ""),
            "RRUPrbTotUlDistBin91To93Percentage": device_data.get("RRU.PrbTotUlDist.Bin91To93Percentage", ""),
            "RRUPrbTotUlDistBin94To96Percentage": device_data.get("RRU.PrbTotUlDist.Bin94To96Percentage", ""),
            "RRUPrbTotUlDistBin97To98Percentage": device_data.get("RRU.PrbTotUlDist.Bin97To98Percentage", ""),
            "RRUPrbTotUlDistBinAbove98Percentage": device_data.get("RRU.PrbTotUlDist.BinAbove98Percentage", ""),
            "L1MPHR1BinLessThanMinus32dBm": device_data.get("L1M.PHR1.BinLessThanMinus32dBm", ""),
            "L1MPHR1BinMinus32ToMinus26dBm": device_data.get("L1M.PHR1.BinMinus32ToMinus26dBm", ""),
            "L1MPHR1BinMinus25ToMinus19dBm": device_data.get("L1M.PHR1.BinMinus25ToMinus19dBm", ""),
            "L1MPHR1BinMinus18ToMinus12dBm": device_data.get("L1M.PHR1.BinMinus18ToMinus12dBm", ""),
            "L1MPHR1BinMinus11ToMinus5dBm": device_data.get("L1M.PHR1.BinMinus11ToMinus5dBm", ""),
            "L1MPHR1BinMinus4To2dBm": device_data.get("L1M.PHR1.BinMinus4To2dBm", ""),
            "L1MPHR1Bin3To9dBm": device_data.get("L1M.PHR1.Bin3To9dBm", ""),
            "L1MPHR1Bin10To16dBm": device_data.get("L1M.PHR1.Bin10To16dBm", ""),
            "L1MPHR1Bin17To23dBm": device_data.get("L1M.PHR1.Bin17To23dBm", ""),
            "L1MPHR1Bin24To31dBm": device_data.get("L1M.PHR1.Bin24To31dBm", ""),
            "L1MPHR1Bin32To37dBm": device_data.get("L1M.PHR1.Bin32To37dBm", ""),
            "L1MPHR1BinGreaterThan38": device_data.get("L1M.PHR1.BinGreaterThan38", ""),
            "RACHPreambleDedCell": device_data.get("RACH.PreambleDedCell", ""),
            "RACHPreambleACell": device_data.get("RACH.PreambleACell", ""),
            "RACHPreambleBCell": device_data.get("RACH.PreambleBCell", ""),
            "RACHPreambleDed.0": device_data.get("RACH.PreambleDed.0", ""),
            "RACHPreambleA.0": device_data.get("RACH.PreambleA.0", ""),
            "RACHPreambleB.0": device_data.get("RACH.PreambleB.0", "")}
        })

    return base

# POST 資料給上層 AI 平台
def post_pm_data(device_type, device_data):
    base_url = "http://192.168.0.40/api/v1/ORAN"
    url = f"{base_url}/{device_type}Data?serverid=10001"
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, headers=headers, json=device_data)
    if response.status_code == 200:
        print(f"Success: {response.json()}")
    else:
        print(f"Error: {response.status_code}, {response.text}")

# 自動發送資料主流程
def send_device_data():
    device_list = fetch_device_names_from_db()
    for device in device_list:
        devicename, device_type, deviceid = device['name'], device['type'], device['deviceid']
        if device_type == 'CU':
            device_data = get_cu_device_data(devicename)
        elif device_type == 'PDU':
            device_data = get_latest_device_data(devicename, INFLUXDB_BUCKET_SOCKET)
        else:
            device_data = get_latest_device_data(devicename, INFLUXDB_BUCKET_PERFORMANCE)

        if not device_data:
            print(f"No data found for {devicename}")
            continue

        response_data = format_response(device_type, device_data, deviceid, devicename)
        post_pm_data(device_type, response_data)

    threading.Timer(60, send_device_data).start()

@app.route('/start', methods=['GET'])
def start_automation():
    send_device_data()
    return jsonify({"status": "Started sending device data every minute"}), 200

if __name__ == '__main__':
    app.run(host='192.168.0.39', port=8080)
