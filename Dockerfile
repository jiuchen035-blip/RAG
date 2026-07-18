FROM python:3.10-slim

WORKDIR /app

# 优先复制依赖缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制全部项目代码
COPY . .

# 腾讯云云托管固定80端口
EXPOSE 80

# 启动生产服务
CMD ["python", "start_prod.py"]