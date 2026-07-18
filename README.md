# Interview RAG Knowledge Base v2 面试知识库系统

## 环境要求
- Windows 10/11
- Python 3.10
- Docker Desktop

## 一键部署中间件
```bash
docker-compose up -d
```
启动的容器及端口：
- PostgreSQL: 5432
- MinIO: 9000 (API), 9001 (Console)
- Milvus: 19530
- Elasticsearch: 9200
- Etcd: 2379

## 配置环境变量
```bash
copy .env.template .env
```
编辑 `.env`，填入 DeepSeek 密钥及相关IP、账号配置。所有参数均有中文注释。

## 安装依赖与启动
```bash
pip install -r requirements.txt
python start_dev.py
```
访问：http://127.0.0.1:8000

## 核心功能教程
1. **系统配置**：进入「系统配置」页，补全模型密钥，点击保存、重载。
2. **知识库管理**：选择切分策略，拖拽上传 MD 文件。等待实时向量化处理。
3. **分片编辑**：点击文档列表的【分片预览】，可在线编辑、合并、删除分片，修改实时同步至 Milvus。
4. **批量运维**：配置模型后，可执行全库去重、生成总结、导出下载。
5. **面试问答**：在「面试问答」页输入问题，系统自动路由模型，展示来源分片及 Token 成本。

## 高频报错修复清单
| 报错现象 | 原因与修复指引 |
|----------|----------------|
| 启动阻断: PG 初始化失败 | 确认 `docker-compose up -d` 成功执行，5432端口未被占用 |
| MilvusException | 检查 Milvus 和 Etcd 容器状态，尝试点击「重建向量集合」 |
| 接口 404 Not Found | 确认请求路径包含 `/api` 前缀，前后端已跨域配置 |
| 0分片提示 | 文档内容为空或切分策略不匹配，请检查文档质量 |
| Flash禁用 | 批量运维按钮自动灰化，需前往配置页补全 `FLASH_API_KEY` |
| list index out of range | 捕获机制已将其转译为中文友好提示，通常因无有效分片导致 |
| 大模型额度耗尽 | 前端展示清晰提示，请充值或更换 API Key |

## Git版本备份
- 初始化基线：`git_backup.bat init`
- 打版本标签：`git_backup.bat tag v1.0`
- 推送远程仓库：`git_backup.bat push`
- 故障回滚：`git_backup.bat rollback v1.0`
