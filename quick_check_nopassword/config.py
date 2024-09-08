# config.py

# InfluxDB 配置信息
INFLUXDB_TOKEN = "l2yrVMPtDQW6Zl9KEVRI2o3LqloJcZue"
INFLUXDB_ORG = "influxdata"
INFLUXDB_BUCKET = "BBU_Info"
INFLUXDB_URL = "http://192.168.0.39:30001"

# VES Collector URL
VES_COLLECTOR_URL = "http://192.168.0.39:30417/eventListener/v7"
VES_COLLECTOR_USERNAME = "sample1"
VES_COLLECTOR_PASSWORD = "sample1"

# Define device connection parameters
device_params = {
    "host": "192.168.135.102",
    "port": 830,
    "username": "netconf",
    "password": "Greigns-2022"
}

# NETCONF filter for retrieving configuration data
filter_str = """<multiran-cm xmlns="urn:reign-altran-o1-cm-multiran:1.0"/>"""
