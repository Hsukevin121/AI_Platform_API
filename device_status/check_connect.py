from ncclient import manager
from pysnmp.hlapi import *
from influxdb_client import InfluxDBClient
import pymysql
import datetime
import pytz  # 引入pytz库
import requests
import config  # 引入配置文件

# MySQL数据库连接信息
db_connection = pymysql.connect(
    host=config.DB_HOST,
    user=config.DB_USER,
    password=config.DB_PASSWORD,
    database=config.DB_NAME
)

# InfluxDB客户端配置
influx_client = InfluxDBClient(url=config.INFLUX_URL, token=config.INFLUX_TOKEN, org=config.INFLUX_ORG)

# Netconf检查
def check_ru_status():
    try:
        response = requests.get(config.NETCONF_API_URL, verify=config.NETCONF_API_VERIFY, headers={"accept": "application/json"})
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
               CommunityData(config.SNMP_COMMUNITY),
               UdpTransportTarget((config.SNMP_TARGET, config.SNMP_PORT)),
               ContextData(),
               ObjectType(ObjectIdentity(config.SNMP_OID)))
    )
    if error_indication or error_status:
        return 2  # 不正常
    else:
        return 1  # 正常

# InfluxDB检查
def check_cu_status():
    query = f'from(bucket: "o1_performance") |> range(start: -5m) |> filter(fn: (r) => r["_measurement"] == "CU01001")'
    result = influx_client.query_api().query(query)
    if len(result) > 0:
        return 1  # 正常
    else:
        return 2  # 不正常

def check_du_status():
    query = f'from(bucket: "o1_performance") |> range(start: -5m) |> filter(fn: (r) => r["_measurement"] == "DU01001")'
    result = influx_client.query_api().query(query)
    if len(result) > 0:
        return 1  # 正常
    else:
        return 2  # 不正常

# 更新MySQL数据库中的设备状态
def update_device_status(deviceid, new_status):
    # 获取当前台湾时间
    tz = pytz.timezone('Asia/Taipei')
    updated_at = datetime.datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

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

    # 更新数据库中的状态、message 和 updated_at
    with db_connection.cursor() as cursor:
        sql = "UPDATE devicelist SET status = %s, message = %s, updated_at = %s WHERE deviceid = %s"
        cursor.execute(sql, (new_status, message, updated_at, deviceid))
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

