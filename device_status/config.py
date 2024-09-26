# config.py

USERNAME = 'AIadmin'
PASSWORD = 'admin0000'

# MySQL数据库配置
DB_HOST = '192.168.0.39'
DB_USER = 'root'
DB_PASSWORD = 'rtlab666'
DB_NAME = 'devicelist'

# InfluxDB客户端配置
INFLUX_URL = "http://192.168.0.39:30001"
INFLUX_TOKEN = "bA4f9O4UZcg2IgCLndENMmhuAT110mdU"
INFLUX_ORG = "influxdata"

# Netconf API 配置
NETCONF_API_URL = "https://192.168.135.102:16000/api/v2/netconf-proxy/oran-mp/rpc/get/all"
NETCONF_API_VERIFY = False  # 是否验证SSL证书

# SNMP 配置
SNMP_COMMUNITY = 'public'
SNMP_TARGET = '192.168.1.10'
SNMP_PORT = 161
SNMP_OID = '1.3.6.1.2.1.1.5.0'
