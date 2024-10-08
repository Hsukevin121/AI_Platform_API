import requests
from flask import Flask, jsonify
from influxdb_client import InfluxDBClient
from datetime import datetime
import pytz
from collections import OrderedDict
import threading

app = Flask(__name__)

# InfluxDB连接配置
INFLUXDB_URL = "http://192.168.0.39:30001"
INFLUXDB_TOKEN = "pDDWqgH1csy4LYVTPKmsoXfAalFgd4pi"
INFLUXDB_ORG = "influxdata"
INFLUXDB_BUCKET_PERFORMANCE = "o1_performance"
INFLUXDB_BUCKET_SOCKET = "socket_info"
INFLUXDB_BUCKET_PDCP = "PDCP_Throughput"

client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)


# Fault ID to Device Type and Status Mapping
fault_to_device_mapping = {
    5: ('RU', 3),
    6: ('RU', 3),
    7: ('RU', 3),
    8: ('RU', 3),
    12: ('RU', 3),
    13: ('RU', 3),
    14: ('RU', 3),
    16: ('CU', 3),
    17: ('DU', 3),
    18: ('RU', 3),
    41: ('CU', 3),
    44: ('CU', 3),
    49: ('CU', 3),
    52: ('DU', 3),
    55: ('DU', 3),
    60: ('DU', 3),
    186: ('RU', 3),
    193: ('RU_DU', 3),
    194: ('RU_DU', 3),
    195: ('RU_DU', 3),
    196: ('DU_CU', 3),
    197: ('DU', 3),
    198: ('DU', 3),
    199: ('CU', 3),
    # 添加更多映射...
}

# 从数据库获取最新的告警数据
def get_alarm_event():
    try:
        query_api = client.query_api()
        # 查询 o1_fault_event bucket 中的告警事件
        query_alarm = '''
        from(bucket: "o1_fault_event")
          |> range(start: -5m)
          |> filter(fn: (r) => r._measurement == "BBU_FM_Event")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
        '''
        
        tables = query_api.query(query_alarm)
        alarm_data = {}
        report_time = None

        # 处理告警事件数据
        for table in tables:
            for record in table.records:
                field = record.get_field()
                value = record.get_value()
                time = record.get_time()
                taiwan_time = convert_to_taiwan_time(time)
                alarm_data[field] = value
                report_time = taiwan_time

        # 添加报告时间
        if report_time:
            alarm_data['EventTime'] = report_time

        # 确保提取 AlarmId 并作为 fault_id 使用
        if 'AlarmId' in alarm_data:
            alarm_data['fault_id'] = alarm_data['AlarmId']
        else:
            print("No AlarmId found in the data.")

        return alarm_data if alarm_data else None
    except Exception as e:
        return {"error": str(e)}



# 动态确定DeviceID并处理告警
def handle_fault(fault_id):
    if fault_id in fault_to_device_mapping:
        device_type, _ = fault_to_device_mapping[fault_id]

        # 获取告警事件数据
        alarm_data = get_alarm_event()
        if not alarm_data:
            print("No alarm data available.")
            return

        # 根据设备类型动态设置DeviceID并发送不同的数据包
        if device_type == "RU":
            ru_alarm_data = get_alarm_event()
            a = 2001
            post_fault_data("RU01001", a, ru_alarm_data)
        elif device_type == "DU":
            du_alarm_data = get_alarm_event()
            a = 3001
            post_fault_data("DU01001", a, du_alarm_data)
        elif device_type == "CU":
            cu_alarm_data = get_alarm_event()
            a = 4001
            post_fault_data("CU01001", a, cu_alarm_data)
        elif device_type == "RU_DU":
            # 发送RU类型封包
            ru_alarm_data = get_alarm_event()
            a = 2001
            post_fault_data("RU01001", a, ru_alarm_data)

            # 发送DU类型封包
            du_alarm_data = get_alarm_event()
            a = 3001
            post_fault_data("DU01001", a, du_alarm_data)

            # RU和DU类型封包后直接返回，避免继续执行
            return

        elif device_type == "DU_CU":
            # 发送DU类型封包
            du_alarm_data = get_alarm_event()
            a = 3001
            post_fault_data("DU01001", a, du_alarm_data)  # 发送DU

            # 发送CU类型封包
            cu_alarm_data = get_alarm_event()
            a = 4001
            post_fault_data("CU01001", a, cu_alarm_data)  # 发送CU
            return
    else:
        print(f"Fault ID {fault_id} not found in mapping.")


# POST设备数据到指定的API
def post_fault_data(device_type, DeviceId, alarm_data):
    base_url = "http://192.168.0.25/api/v1/ORAN/O1Fault"
    server_id = 10001
    url = f"{base_url}?serverid={server_id}"

    # 请求头
    headers = {
        'Content-Type': 'application/json'
    }

    formatted_data = {
            "DeviceId": DeviceId,
            "DeviceType": device_type,
            "AlarmId": alarm_data.get("AlarmId",0),
            "EventTime": alarm_data.get("EventTime", ""),
            "EventSeverity": alarm_data.get("EventServerity", ""),
            "SystemDN": alarm_data.get("systemDN", ""),
            "AlarmType": alarm_data.get("AlarmType", ""),
            "ProbableCause": alarm_data.get("ProbableCause", ""),
            "IsCleared": alarm_data.get("isCleared", "")
    }



    # 发送POST请求
    response = requests.post(url, headers=headers, json=formatted_data)
    if response.status_code == 200:
        print(f"Success: {response.json()}")
    else:
        print(f"Error: {response.status_code}, {response.text}")


# 将 UTC 时间转换为台湾时间
def convert_to_taiwan_time(utc_time):
    if isinstance(utc_time, str):
        utc_time = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
    taiwan_tz = pytz.timezone('Asia/Taipei')
    taiwan_time = utc_time.astimezone(taiwan_tz)
    return taiwan_time.strftime("%Y-%m-%d %H:%M:%S")

# 从InfluxDB获取最新设备数据
def get_latest_device_data(device_name, bucket_name, measurement_filter=None):
    try:
        query_api = client.query_api()
        measurement_filter = measurement_filter or f'r._measurement == "{device_name}"'
        
        query = f'''
        from(bucket: "{bucket_name}")
          |> range(start: -5m)
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

        return device_data if device_data else None
    except Exception as e:
        return {"error": str(e)}

# 查询CU设备，合并多个bucket
def get_cu_device_data(device_name):
    try:
        query_api = client.query_api()

        # 查询o1_performance bucket中的数据
        query_performance = f'''
        from(bucket: "{INFLUXDB_BUCKET_PERFORMANCE}")
          |> range(start: -5m)
          |> filter(fn: (r) => r._measurement == "{device_name}")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
        '''

        # 查询PDCP_Throughput bucket中的数据
        query_pdcp = f'''
        from(bucket: "{INFLUXDB_BUCKET_PDCP}")
          |> range(start: -5m)
          |> filter(fn: (r) => r._measurement == "ue_sum_info" or r._measurement == "ue_info")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
        '''

        performance_tables = query_api.query(query_performance)
        pdcp_tables = query_api.query(query_pdcp)

        device_data = {}
        report_time = None

        # 处理o1_performance数据
        for table in performance_tables:
            for record in table.records:
                field = record.get_field()
                value = record.get_value()
                time = record.get_time()
                taiwan_time = convert_to_taiwan_time(time)
                device_data[field] = value
                report_time = taiwan_time

        # 处理PDCP_Throughput数据
        for table in pdcp_tables:
            for record in table.records:
                field = record.get_field()
                value = record.get_value()
                device_data[field] = value

        if report_time:
            device_data['ReportTime'] = report_time

        return device_data if device_data else None
    except Exception as e:
        return {"error": str(e)}

# 将设备数据POST到相应的API
def post_pm_data(device_type, device_data):
    base_url = "http://192.168.0.25/api/v1/ORAN"
    server_id = 10001
    url = f"{base_url}/{device_type}Data?serverid={server_id}"

    # 请求头
    headers = {
        'Content-Type': 'application/json'
    }

    # 发送POST请求
    response = requests.post(url, headers=headers, json=device_data)
    if response.status_code == 200:
        print(f"Success: {response.json()}")
    else:
        print(f"Error: {response.status_code}, {response.text}")

# 响应格式化函数
def format_response(device_type, device_data):
    if device_type == 'PDU':
        # 确保 TotalPowerload 和其他字段为正确的类型
        total_powerload = int(device_data.get("inFeedPowerLoad_index_1", 0))
        total_current = float(device_data.get("inFeedCurrent_index_1", 0))

        return OrderedDict({
            "NumofSocket": 4,  # 确定插座数量
            "TotalCurrent": total_current,  # 确保为浮点数类型
            "TotalPowerload": total_powerload,  # 确保为整数类型
            "ReportTime": device_data.get("ReportTime", ""),
            "Socket": [
                {
                    "SocketId": i,
                    "SocketVoltage": device_data.get(f"outVoltage_index_{i+1}", 0),  # 默认为 0
                    "SocketCurrent": device_data.get(f"outCurrent_index_{i+1}", 0),  # 默认为 0
                    "SocketPowerload": device_data.get(f"outPowerLoad_index_{i+1}", 0),  # 默认为 0
                    "InFeedPowerEnergy": device_data.get("inFeedPowerEnergy_index_1", 0)  # 默认为 0
                } for i in range(4)  # 创建 4 个插座条目
            ]
        })
    elif device_type == 'RU':
        return OrderedDict({
            "DeviceId": device_data.get("DeviceId", ""),
            "DeviceType": "RU01001",
            "TxAttenuation": device_data.get("tx_attenuation", ""),
            "ReportTime": device_data.get("ReportTime", "")
        })
    elif device_type == 'DU':
        return  OrderedDict({
            "DeviceId": 3001,
            "DeviceType": "DU01001",
            "ReportTime": device_data.get("ReportTime", ""),
                    "PmData": OrderedDict({
            "RRUPrbTotDl": device_data.get("RRU.PrbTotDl", ""),
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
            "RACHPreambleB.0": device_data.get("RACH.PreambleB.0", "")
        })
    })
    elif device_type == 'CU':
        num_of_ue = int(device_data.get("num_of_ue", "0"))
        ue_list = [
            {
                "UeId": ue_id,
                "UlTp": device_data.get(f"ul_tp", ""),
                "UlPkt": device_data.get(f"ul_pkt", ""),
                "DlTp": device_data.get(f"dl_tp", ""),
                "DlPkt": device_data.get(f"dl_pkt", "")
            } for ue_id in range(num_of_ue)
        ]
        return OrderedDict({
            "DeviceId": "4001",
            "DeviceType": "CU01001",
            "ReportTime": device_data.get("ReportTime", ""),
            "PmData": {
                "PAGReceivedNbrCnInitiated": device_data.get("PAG.ReceivedNbrCnInitiated", ""),
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
                "SysCellAvail": device_data.get("Sys.CellAvail", "")
            },
            "NumofUe": num_of_ue,
            "TotalUlTp": device_data.get("total_ul_tp", ""),
            "TotalUlPkt": device_data.get("total_ul_pkt", ""),
            "TotalDlTp": device_data.get("total_dl_tp", ""),
            "TotalDlPkt": device_data.get("total_dl_pkt", ""),
            "Ue": ue_list
        })



# 自动化定时发送设备数据的函数
def send_device_data():
    device_names = ['RU01001', 'DU01001', 'CU01001', 'PDU01001']
    
    for devicename in device_names:
        if devicename.startswith("PDU"):
            device_data = get_latest_device_data(devicename, INFLUXDB_BUCKET_SOCKET)
            device_type = "PDU"
        elif devicename.startswith("RU"):
            device_data = get_latest_device_data(devicename, INFLUXDB_BUCKET_PERFORMANCE)
            device_type = "RU"
        elif devicename.startswith("DU"):
            device_data = get_latest_device_data(devicename, INFLUXDB_BUCKET_PERFORMANCE)
            device_type = "DU"
        elif devicename.startswith("CU"):
            device_data = get_cu_device_data(devicename)
            device_type = "CU"
        else:
            print(f"Unsupported device type for {devicename}")
            continue

        if not device_data:
            print(f"No data found for {devicename}")
            continue

        # 格式化响应数据
        response_data = format_response(device_type, device_data)
        
        # POST设备数据到指定的API路径
        post_pm_data(device_type, response_data)
  
    alarm_data = get_alarm_event()
    print("Alarm Data:", alarm_data)
    if alarm_data:
        fault_id = alarm_data.get("fault_id")  # 确保从 alarm_data 中获取 fault_id
        if fault_id:
            print(f"Handling fault ID: {fault_id}")
            handle_fault(fault_id)
        else:
            print("No fault ID found.")
    else:
        print("No alarm data found.")
   
    # 每一分钟执行一次
    threading.Timer(60, send_device_data).start()

# 启动自动发送数据
@app.route('/start', methods=['GET'])
def start_automation():
    send_device_data()
    return jsonify({"status": "Started sending device data every minute"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
