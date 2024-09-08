from ncclient import manager
from pysnmp.hlapi import *
from influxdb_client import InfluxDBClient
import pymysql
import datetime
import requests


# MySQL数据库连接信息
db_connection = pymysql.connect(
    host='localhost',
    user='root',
    password='rtlab666',
    database='devicelist'
)

# InfluxDB客户端配置
influx_client = InfluxDBClient(url="http://192.168.0.39:30001", token="l2yrVMPtDQW6Zl9KEVRI2o3LqloJcZue", org="influxdata")

# Netconf检查
def check_ru_status():
    try:
        response = requests.get("https://192.168.135.102:16000/api/v2/netconf-proxy/oran-mp/rpc/get/all", verify=False, headers={"accept": "application/json"})
        response.raise_for_status()
        if "ACTIVE" in response.text:
            return 1  # 正常
        else:
            return 2  # 不正常
    except requests.RequestException as e:
        return 2  # 处理请求异常时返回不正常状态

# SNMP检查
def check_pdu_status():
    error_indication, error_status, error_index, var_binds = next(
        getCmd(SnmpEngine(),
               CommunityData('public'),
               UdpTransportTarget(('192.168.1.10', 161)),
               ContextData(),
               ObjectType(ObjectIdentity('1.3.6.1.2.1.1.5.0')))
    )
    if error_indication or error_status:
        return 2  # 不正常
    else:
        return 1  # 正常

# InfluxDB检查
def check_cu_status():
    current_time = datetime.datetime.utcnow()
    query = f'from(bucket: "o1_performance") |> range(start: -5m) |> filter(fn: (r) => r["_measurement"] == "CU01001")'
    result = influx_client.query_api().query(query)
    if len(result) > 0:
        return 1  # 正常
    else:
        return 2  # 不正常

def check_du_status():
    current_time = datetime.datetime.utcnow()
    query = f'from(bucket: "o1_performance") |> range(start: -5m) |> filter(fn: (r) => r["_measurement"] == "DU01001")'
    result = influx_client.query_api().query(query)
    if len(result) > 0:
        return 1  # 正常
    else:
        return 2  # 不正常


# 更新MySQL数据库中的设备状态
def update_device_status(deviceid, new_status):
    # 先检查当前设备的status
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT status FROM devicelist WHERE deviceid = %s", (deviceid,))
        current_status = cursor.fetchone()

    if current_status:
        current_status = current_status[0]  # 提取查询结果中的status

    # 检查当前状态是否为3
    if current_status == 3:
        if new_status == 1:
            print(f"Device {deviceid} is currently in status 3, and cannot be updated to status 1. No changes made.")
            return  # 不进行更新
        elif new_status == 2:
            message = "The device is disconnected"
            # 允许更新status为2
        else:
            print(f"Unexpected status for device {deviceid}. No changes made.")
            return  # 不进行更新
    else:
        # 其他状态更新正常逻辑
        if new_status == 1:
            message = "The device is healthy"
        elif new_status == 2:
            message = "The device is disconnected"

    # 更新数据库中的状态和message
    with db_connection.cursor() as cursor:
        sql = "UPDATE devicelist SET status = %s, message = %s WHERE deviceid = %s"
        cursor.execute(sql, (new_status, message, deviceid))
        db_connection.commit()

# 定时任务：检查设备状态并更新数据库
def check_devices():
    ru_status = check_ru_status()
    update_device_status(2001, ru_status)
    
    pdu_status = check_pdu_status()
    update_device_status(5001, pdu_status)
    
    du_status = check_du_status()
    update_device_status(3001, du_status)
    
    cu_status = check_cu_status()
    update_device_status(4001, cu_status)

if __name__ == '__main__':
    check_devices()
