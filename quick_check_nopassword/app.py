import glob
import os
import time
import xml.etree.ElementTree as ET
from flask import Flask, jsonify
import requests
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime, timedelta

# InfluxDB 配置
bucket = "o1_performance"
org = "influxdata"
token = "bzgBwlyDG8ZWBo0LP2hpbJ48I9zhZtMR"
url = "http://192.168.0.39:30001"
client = InfluxDBClient(url=url, token=token)
write_api = client.write_api(write_options=SYNCHRONOUS)

dynamic_param_sets = {}  # 用于记录每个 measurement 的历史参数集合

app = Flask(__name__)

# Function to check if InfluxDB is alive
def check_influxdb_status():
    """
    检查 InfluxDB 是否活着（通过 /ping API）。
    """
    ping_url = f"{url}/ping"  # 避免冲突，使用局部变量 ping_url
    try:
        response = requests.get(ping_url, timeout=5)
        if response.status_code == 204:  # InfluxDB /ping 成功返回 204
            return True
        return False
    except Exception as e:
        print(f"InfluxDB status check failed: {e}")
        return False

# 从 SFTP 文件中提取参数和值
def extract_parameters_from_sftp(file_path):
    """
    从 SFTP 文件中提取参数和值
    """
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        # 创建 measType 字典
        meas_types = {}
        for measType in root.findall('.//{http://www.3gpp.org/ftp/specs/archive/28_series/28.532#measData}measType'):
            p_value = measType.attrib.get('p')
            meas_types[p_value] = measType.text

        # 遍历 measValue 标签提取数据
        parameters = {}
        for measValue in root.findall('.//{http://www.3gpp.org/ftp/specs/archive/28_series/28.532#measData}measValue'):
            for r in measValue.findall('.//{http://www.3gpp.org/ftp/specs/archive/28_series/28.532#measData}r'):
                p_value = r.attrib.get('p')
                meas_name = meas_types.get(p_value, f"metric_{p_value}")
                try:
                    parameters[meas_name] = float(r.text)
                except (ValueError, TypeError):
                    print(f"Invalid value for {meas_name}: {r.text}")
                    continue
        return parameters
    except ET.ParseError:
        print(f"Error: Unable to parse the XML file: {file_path}")
        return {}

# 从 InfluxDB 查询数据并进行比对
def check_influxdb_data_consistency(measurement, sftp_params):
    """
    比对 SFTP 参数和 InfluxDB 中的最新数据
    """
    query = (
        f'from(bucket: "{bucket}") '
        f'|> range(start: -5m) '
        f'|> filter(fn: (r) => r["_measurement"] == "{measurement}") '
        f'|> filter(fn: (r) => exists r["_value"]) '
        f'|> last()'
    )

    print(f"Executing query: {query}")

    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/vnd.flux"
    }
    query_url = f"{url}/api/v2/query?org={org}"

    try:
        response = requests.post(query_url, headers=headers, data=query.encode('utf-8'))
        if response.status_code != 200:
            print(f"InfluxDB query failed: {response.text}")
            return False

        # 解析 InfluxDB 返回的数据
        rows = response.text.strip().split("\n")
        if not rows or len(rows) < 2:
            print("No data rows found in InfluxDB response.")
            return False

        # 提取字段和值
        header = rows[0].split(",")
        field_index = header.index("_field")
        value_index = header.index("_value")

        influxdb_params = {}
        for row in rows[1:]:
            if not row.startswith("#") and row.strip():  # 跳过注释和空行
                columns = row.split(",")
                field_value = columns[field_index].strip()
                try:
                    influxdb_params[field_value] = float(columns[value_index])
                except ValueError:
                    print(f"Invalid value for {field_value}: {columns[value_index]}")

        # 比对 SFTP 参数和值
        mismatches = []
        for field, sftp_value in sftp_params.items():
            influx_value = influxdb_params.get(field)
            if influx_value is None:
                mismatches.append(f"{field}: Missing in InfluxDB")
            elif influx_value != sftp_value:
                mismatches.append(f"{field}: SFTP={sftp_value}, InfluxDB={influx_value}")

        if mismatches:
            print(f"Mismatches detected for {measurement}: {mismatches}")
            return False

        print(f"Data consistency check passed for {measurement}.")
        return True
    except Exception as e:
        print(f"Error checking InfluxDB data consistency: {e}")
        return False

def get_latest_file(directory):
    """
    获取目录中最后修改的 XML 文件
    """
    xml_files = glob.glob(f"{directory}/*.xml")
    if not xml_files:
        print(f"No XML files found in {directory}.")
        return None
    latest_file = max(xml_files, key=os.path.getmtime)
    print(f"Latest file in {directory}: {latest_file}")
    return latest_file

@app.route('/api/v1/ORAN/quick_check', methods=['GET'])
def quick_check():
    """
    进行 SFTP 和 InfluxDB 数据比对。
    """
    report_time = (datetime.now() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")

    # Step 1: Check if InfluxDB is alive
    if not check_influxdb_status():
        return jsonify({
            "reporttime": report_time,
            "status": "error",
            "message": "InfluxDB status check failed."
        }), 400

    # Step 2: 动态获取最新文件路径
    sftp_files = {
        "CU01001": get_latest_file("/app/sftp/CU"),
        "DU01001": get_latest_file("/app/sftp/DU")
    }

    for measurement, file_path in sftp_files.items():
        if not file_path:
            return jsonify({
                "reporttime": report_time,
                "status": "error",
                "message": f"No file found for measurement: {measurement}."
            }), 400

        sftp_params = extract_parameters_from_sftp(file_path)

        # Step 3: 比对 SFTP 参数和 InfluxDB 数据
        if not check_influxdb_data_consistency(measurement, sftp_params):
            return jsonify({
                "reporttime": report_time,
                "status": "error",
                "message": f"Data inconsistency detected for measurement: {measurement}."
            }), 400

    return jsonify({
        "reporttime": report_time,
        "status": "success",
        "message": "Data checks passed successfully."
    }), 200

@app.route('/api/v1/debug/test', methods=['GET'])
def debug_test():
    """
    测试 Flask 能否访问文件目录
    """
    cu_files = glob.glob("/home/sftp/CU/*.xml")
    du_files = glob.glob("/home/sftp/DU/*.xml")
    return jsonify({
        "CU_files": cu_files,
        "DU_files": du_files,
        "working_directory": os.getcwd()
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
