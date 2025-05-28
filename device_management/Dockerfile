# 使用官方的 Python 基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 将当前目录的内容复制到容器中的 /app 目录
COPY . /app

# 安装所需的 Python 包
RUN pip install --no-cache-dir -r requirements.txt

# 暴露应用程序运行的端口
EXPOSE 8080

# 设置环境变量以告诉 Flask 在容器启动时运行应用程序
ENV FLASK_APP=app.py

# 确保 Flask 使用生产环境配置
ENV FLASK_ENV=production

# 运行 Flask 应用程序
CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
