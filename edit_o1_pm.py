from ncclient import manager

# NETCONF 服务器的连接信息
host = "your_netconf_server_ip"
port = 830  # 默认为 830
username = "your_username"
password = "your_password"

# XML 配置内容
config_xml = """
<config>
  <multiran-pm xmlns="urn:reign-altran-o1-pm-multiran:1.0">
    <ran-id>ran1</ran-id>
    <reign-pm-measurement-job-control>
      <PerfMetricJob>
        <id>gNB_CU</id>
        <attributes>
          <administrativeState>UNLOCKED</administrativeState>
          <jobId>gNB_CU</jobId>
          <performanceMetrics>gNB_CU</performanceMetrics>
          <granularityPeriod>60</granularityPeriod>
          <fileReportingPeriod>1</fileReportingPeriod>
          <fileLocation>sftp://sftpuser:ubuntu@192.168.135.76:22/uploads</fileLocation>
        </attributes>
      </PerfMetricJob>
      <PerfMetricJob>
        <id>gNB_DU</id>
        <attributes>
          <administrativeState>UNLOCKED</administrativeState>
          <jobId>gNB_DU</jobId>
          <performanceMetrics>gNB_DU</performanceMetrics>
          <granularityPeriod>60</granularityPeriod>
          <fileReportingPeriod>1</fileReportingPeriod>
          <fileLocation>sftp://sftpuser:ubuntu@192.168.135.76:22/uploads</fileLocation>
        </attributes>
      </PerfMetricJob>
    </reign-pm-measurement-job-control>
  </multiran-pm>
  <multiran-pm xmlns="urn:reign-altran-o1-pm-multiran:1.0">
    <ran-id>ran2</ran-id>
    <reign-pm-measurement-job-control>
      <PerfMetricJob>
        <id>gNB_CU</id>
        <attributes>
          <administrativeState>LOCKED</administrativeState>
          <jobId>gNB_CU</jobId>
          <performanceMetrics>gNB_CU</performanceMetrics>
          <granularityPeriod>60</granularityPeriod>
          <fileReportingPeriod>1</fileReportingPeriod>
          <fileLocation>sftp_info</fileLocation>
        </attributes>
      </PerfMetricJob>
      <PerfMetricJob>
        <id>gNB_DU</id>
        <attributes>
          <administrativeState>LOCKED</administrativeState>
          <jobId>gNB_DU</jobId>
          <performanceMetrics>gNB_DU</performanceMetrics>
          <granularityPeriod>60</granularityPeriod>
          <fileReportingPeriod>1</fileReportingPeriod>
          <fileLocation>sftp_info</fileLocation>
        </attributes>
      </PerfMetricJob>
    </reign-pm-measurement-job-control>
  </multiran-pm>
</config>
"""

# 连接到 NETCONF 服务器并应用配置
with manager.connect(
    host=host,
    port=port,
    username=username,
    password=password,
    hostkey_verify=False
) as m:
    # 执行配置
    response = m.edit_config(target="running", config=config_xml)
    print(response)
