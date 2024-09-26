from flask import Flask, request, jsonify
from influxdb_client import InfluxDBClient
from datetime import datetime
import pytz
from collections import OrderedDict
import config  # 引入配置文件

app = Flask(__name__)

# InfluxDB连接配置
client = InfluxDBClient(url=config.INFLUXDB_URL, token=config.INFLUXDB_TOKEN, org=config.INFLUXDB_ORG)

# 将 UTC 时间转换为台湾时间
def convert_to_taiwan_time(utc_time):
    if isinstance(utc_time, str):  # 如果时间是字符串类型
        utc_time = datetime.fromisoformat(utc_time.replace("Z", "+00:00"))
    taiwan_tz = pytz.timezone('Asia/Taipei')
    taiwan_time = utc_time.astimezone(taiwan_tz)
    return taiwan_time.strftime("%Y-%m-%d %H:%M:%S")

# 通用函数：从InfluxDB提取最新设备数据
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

        return device_data if device_data else None
    except Exception as e:
        return {"error": str(e)}

# 查询CU设备，合并多个bucket
def get_cu_device_data(device_name):
    try:
        query_api = client.query_api()

        # 查询o1_performance bucket中的数据
        query_performance = f'''
        from(bucket: "{config.INFLUXDB_BUCKET_PERFORMANCE}")
          |> range(start: -1h)
          |> filter(fn: (r) => r._measurement == "{device_name}")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 1)
        '''

        # 查询PDCP_Throughput bucket中的数据
        query_pdcp = f'''
        from(bucket: "{config.INFLUXDB_BUCKET_PDCP}")
          |> range(start: -1h)
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

# 响应格式化函数
def format_response(device_type, device_data):
    if device_type == 'PDU':
        return OrderedDict({
            "DeviceId": device_data.get("DeviceId", ""),
            "DeviceType": "PDU01001",
            "NumofSocket": 4,
            "TotalCurrent": device_data.get("inFeedCurrent_index_1", ""),
            "TotalPowerload": device_data.get("inFeedPowerLoad_index_1", ""),
            "ReportTime": device_data.get("ReportTime", ""),
            "Socket": [
                {f"SocketId": str(i+1),
                 "SocketVoltage": device_data.get(f"outVoltage_index_{i+1}", ""),
                 "SocketCurrent": device_data.get(f"outCurrent_index_{i+1}", ""),
                 "SocketPowerload": device_data.get(f"outPowerLoad_index_{i+1}", ""),
                 "InFeedPowerEnergy": device_data.get("inFeedPowerEnergy_index_1", "")
                 } for i in range(4)
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

@app.route('/api/v1/ORAN/deviceList', methods=['GET'])
def get_device_info():
    devicename = request.args.get('Info')
    print(f"Received device name: {devicename}")  # 调试信息
    if not devicename:
        return jsonify({"error": "Device name not provided", "status": 400}), 400

    # 检查设备类型
    if devicename.startswith("PDU"):
        device_data = get_latest_device_data(devicename, config.INFLUXDB_BUCKET_SOCKET)
        device_type = "PDU"
    elif devicename.startswith("RU"):
        device_data = get_latest_device_data(devicename, config.INFLUXDB_BUCKET_PERFORMANCE)
        device_type = "RU"
    elif devicename.startswith("DU"):
        device_data = get_latest_device_data(devicename, config.INFLUXDB_BUCKET_PERFORMANCE)
        device_type = "DU"
    elif devicename.startswith("CU"):
        device_data = get_cu_device_data(devicename)
        device_type = "CU"
    else:
        print(f"Unsupported device type for {devicename}")  # 调试信息
        return jsonify({"error": "Unsupported device type", "status": 400}), 400

    if not device_data:
        return jsonify({"error": "Device data not found", "status": 404}), 404

    response_data = format_response(device_type, device_data)
    return jsonify(response_data), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
