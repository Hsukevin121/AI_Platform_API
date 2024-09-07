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
influx_client = InfluxDBClient(url="http://192.168.0.39:30001", token="RyGBIs41IMTRR0YHAi0q2oKJDh6zzIjQ", org="influxdata")

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
    query = f'from(bucket: "o1_performance") |> range(start: -5m) |> filter(fn: (r) => r["_measurement"] == "ran1_gNB_CU_PM")'
    result = influx_client.query_api().query(query)
    if len(result) > 0:
        return 1  # 正常
    else:
        return 2  # 不正常

def check_du_status():
    current_time = datetime.datetime.utcnow()
    query = f'from(bucket: "o1_performance") |> range(start: -5m) |> filter(fn: (r) => r["_measurement"] == "ran1_gNB_DU_PM")'
    result = influx_client.query_api().query(query)
    if len(result) > 0:
        return 1  # 正常
    else:
        return 2  # 不正常


# 更新MySQL数据库中的设备状态
def update_device_status(deviceid, status):
    with db_connection.cursor() as cursor:
        sql = "UPDATE devicelist SET status = %s WHERE deviceid = %s"
        cursor.execute(sql, (status, deviceid))
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
