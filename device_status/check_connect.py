from influxdb_client import InfluxDBClient
import pymysql
import datetime
import pytz
import config

# MySQL 連線
db_connection = pymysql.connect(
    host=config.DB_HOST,
    user=config.DB_USER,
    password=config.DB_PASSWORD,
    database=config.DB_NAME
)

# InfluxDB 連線
influx_client = InfluxDBClient(
    url=config.INFLUX_URL,
    token=config.INFLUX_TOKEN,
    org=config.INFLUX_ORG
)

# 根據資料表名稱決定該查詢哪個 InfluxDB bucket
def get_bucket_by_table(table_name):
    if table_name == "PDUdevicelist":
        return "socket_info"
    else:
        return "o1_performance"

# 查詢 InfluxDB 中某裝置最近 5 分鐘是否有資料
def check_influx_status(devicename, device_table):
    try:
        bucket = get_bucket_by_table(device_table)
        query = f'''
        from(bucket: "{bucket}")
        |> range(start: -5m)
        |> filter(fn: (r) => r["_measurement"] == "{devicename}")
        '''
        result = influx_client.query_api().query(query)
        return 1 if len(result) > 0 else 2
    except Exception as e:
        print(f"[Influx 錯誤] 查詢 {devicename}（{device_table}）時出現錯誤：{e}")
        return 2

# 更新 MySQL 中的裝置狀態
def update_device_status(device_table, devicename, deviceid, status):
    tz = pytz.timezone('Asia/Taipei')
    updated_at = datetime.datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    message = "The device is healthy" if status == 1 else "The device is disconnected"

    try:
        with db_connection.cursor() as cursor:
            update_sql = f'''
                UPDATE {device_table}
                SET status = %s, message = %s, updated_at = %s
                WHERE deviceid = %s
            '''
            cursor.execute(update_sql, (status, message, updated_at, deviceid))
            db_connection.commit()
            print(f"[更新] {device_table} 中 {devicename}（id={deviceid}）狀態更新為 {status}")
    except Exception as e:
        print(f"[MySQL 錯誤] 更新 {device_table} 中 {devicename}（id={deviceid}）時出現錯誤：{e}")

# 查詢所有資料表與裝置，逐筆更新狀態
def fetch_all_devices_and_update():
    tables = ["RUdevicelist", "CUdevicelist", "DUdevicelist", "PDUdevicelist"]

    with db_connection.cursor() as cursor:
        for table in tables:
            try:
                cursor.execute(f"SELECT devicename, deviceid FROM {table}")
                rows = cursor.fetchall()
                for row in rows:
                    devicename = row[0]
                    deviceid = row[1]
                    status = check_influx_status(devicename, table)
                    update_device_status(table, devicename, deviceid, status)
            except Exception as e:
                print(f"[錯誤] 查詢 {table} 或更新裝置狀態時出現錯誤：{e}")

# 主程式
if __name__ == '__main__':
    fetch_all_devices_and_update()
