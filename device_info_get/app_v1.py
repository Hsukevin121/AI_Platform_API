from flask import Flask, request, Response, jsonify
from influxdb_client import InfluxDBClient
from datetime import datetime
import pytz
from collections import OrderedDict
import json

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

# cu因為需要把2個bucket合併，所以另外寫一個副程式
def get_cu_device_data(device_name):
    query_api = client.query_api()

    # 查询o1_performance bucket中的数据
    query_performance = f'''
    from(bucket: "{INFLUXDB_BUCKET_PERFORMANCE}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "{device_name}")
      |> sort(columns: ["_time"], desc: true)
      |> limit(n: 1)
    '''

    # 查询PDCP_Throughput bucket中的数据
    query_pdcp = f'''
    from(bucket: "{INFLUXDB_BUCKET_PDCP}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "ue_sum_info" or r["_measurement"] == "ue_info")
      |> sort(columns: ["_time"], desc: true)
      |> limit(n: 1)
    '''

    performance_tables = query_api.query(query_performance)
    pdcp_tables = query_api.query(query_pdcp)

    device_data = {}
    report_time = None  # 用于存储从 o1_performance bucket 中提取的时间

    # 处理o1_performance数据
    for table in performance_tables:
        for record in table.records:
            field = record.get_field()
            value = record.get_value()
            time = record.get_time()
            taiwan_time = convert_to_taiwan_time(time)  # 转换为台湾时间
            device_data[field] = value
            report_time = taiwan_time  # 保存 o1_performance 的报告时间

    # 处理PDCP_Throughput数据
    for table in pdcp_tables:
        for record in table.records:
            field = record.get_field()
            value = record.get_value()
            device_data[field] = value

    # 只使用从 o1_performance 中获取的报告时间
    if report_time:
        device_data['ReportTime'] = report_time

    return device_data



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
############################################################################################
# PDU 格式響應
def format_pdu_response(device_data):
    return OrderedDict({
        "Deviceid": device_data.get("DeviceId", ""),
        "DeviceType": "PDU01001",
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
############################################################################################
# RU 格式響應
def format_ru_response(device_data):
    return OrderedDict({
        "Deviceid": device_data.get("DeviceId", ""),
        "DeviceType": "RU01001",
        "TxAttenuation": device_data.get("tx_attenuation", ""),
        "ReportTime": device_data.get("ReportTime", ""),
    })
############################################################################################
# DU 格式響應
def format_du_response(device_data):
    return OrderedDict({
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

#############################################################################################
# CU 格式響應
def format_cu_response(device_data):
    num_of_ue = int(device_data.get("num_of_ue", "0"))  # 获取UE的数量
    ue_list = []

    # 动态生成UE列表
    for ue_id in range(num_of_ue):
        ue_data = {
            "UeId": ue_id,
            "UlTp": device_data.get(f"ul_tp", ""),
            "UlPkt": device_data.get(f"ul_pkt", ""),
            "DlTp": device_data.get(f"dl_tp", ""),
            "DlPkt": device_data.get(f"dl_pkt", "")
        }
        ue_list.append(ue_data)

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
        "NumofUe": num_of_ue,  # 动态设置UE数量
        "TotalUlTp": device_data.get("total_ul_tp", ""),
        "TotalUlPkt": device_data.get("total_ul_pkt", ""),
        "TotalDlTp": device_data.get("total_dl_tp", ""),
        "TotalDlPkt": device_data.get("total_dl_pkt", ""),
        "Ue": ue_list  # 动态生成的UE列表
    })




# API 路由
@app.route('/api/v1/ORAN/deviceList', methods=['GET'])
def get_device_info():
    devicename = request.args.get('Info')
    if not devicename:
        return jsonify({"error": "Device name not provided"}), 400

    # 处理 PDU 设备
    if devicename.startswith("PDU"):
        bucket_name = INFLUXDB_BUCKET_SOCKET
        device_data = get_latest_device_data(devicename, bucket_name)
        if not device_data:
            return jsonify({"error": "Device data not found"}), 404
        
        # 格式化 PDU 响应
        response_data = format_pdu_response(device_data)
        
        # 手动序列化 JSON 并返回
        return Response(json.dumps(response_data), mimetype='application/json')

    elif devicename.startswith("RU"):
        bucket_name = INFLUXDB_BUCKET_PERFORMANCE
        device_data = get_latest_device_data(devicename, bucket_name)
        if not device_data:
            return jsonify({"error": "Device data not found"}), 404
        
        response_data = format_ru_response(device_data)
        
        return Response(json.dumps(response_data), mimetype='application/json')

    elif devicename.startswith("DU"):
        bucket_name = INFLUXDB_BUCKET_PERFORMANCE
        device_data = get_latest_device_data(devicename, bucket_name)
        if not device_data:
            return jsonify({"error": "Device data not found"}), 404
        
        response_data = format_du_response(device_data)
        
        return Response(json.dumps(response_data), mimetype='application/json')
    
    elif devicename.startswith("CU"):
        device_data = get_cu_device_data(devicename)
        if not device_data:
            return jsonify({"error": "Device data not found"}), 404
        
        response_data = format_cu_response(device_data)
        return Response(json.dumps(response_data), mimetype='application/json')
    
    return jsonify({"error": "Unsupported device type"}), 400

# 主函数
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
