# 使用官方的 Python 3.8 基础镜像
FROM python:3.8-slim

# 设置工作目录
WORKDIR /app

# 将当前目录中的内容复制到容器中
COPY . /app

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 暴露应用程序运行的端口
EXPOSE 8080

# 运行 Flask 应用
CMD ["python", "app.py"]
