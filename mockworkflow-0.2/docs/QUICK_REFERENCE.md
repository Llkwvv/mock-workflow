# 快速参考指南

## 常用命令

### 启动服务
```bash
.venv/bin/python3 start_backend.py
```

### 运行测试
```bash
.venv/bin/python3 -m pytest tests/unit/test_auth.py -v
```

### 查看审计日志
```bash
tail -f .audit.log
```

### 检查API健康
```bash
curl http://localhost:8000/api/health
```

## API 端点

### 认证相关

#### 登录
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password": "your_password"}' \
  -c cookies.txt
```

#### 获取CSRF Token
```bash
curl http://localhost:8000/api/auth/csrf
```

#### 检查认证状态
```bash
curl http://localhost:8000/api/auth/me -b cookies.txt
```

#### 登出
```bash
curl -X POST http://localhost:8000/api/auth/logout -b cookies.txt
```

### 系统相关

#### 健康检查
```bash
curl http://localhost:8000/api/health
```

#### 指标
```bash
curl http://localhost:8000/api/metrics
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MOCKWORKFLOW_WEB_PASSWORD` | 登录密码 | `None`（无认证） |
| `MOCKWORKFLOW_SECURE_COOKIES` | 启用Secure Cookie | `0` |
| `MOCKWORKFLOW_ENVIRONMENT` | 环境模式 | `development` |

## 配置文件

- `.sessions.json` - 会话数据
- `.audit.log` - 审计日志
- `pyproject.toml` - 项目配置
- `.env` - 环境变量

## 安全特性

✅ bcrypt密码哈希  
✅ IP登录失败锁定（5次/15分钟）  
✅ 完整审计日志  
✅ CSRF Token保护  
✅ 安全响应头  
✅ HttpOnly Cookie  
✅ SameSite=Lax  
✅ 生产环境Secure Cookie

## 测试覆盖率

- 单元测试：11/11 ✅
- 认证流程：完整 ✅
- 安全功能：完整 ✅

## 审计日志格式

```json
{"ts":"2026-06-10T09:17:49.633578+00:00","event":"login_failure","remote_addr":"127.0.0.1","reason":"invalid_password"}
{"ts":"2026-06-10T09:17:51.121596+00:00","event":"login_success","remote_addr":"127.0.0.1","user":"unknown"}
{"ts":"2026-06-10T09:17:54.535206+00:00","event":"logout","remote_addr":"127.0.0.1","user":"unknown"}
```

## 故障排除

### 端口被占用
```bash
lsof -ti:8000 | xargs kill -9
```

### 权限问题
```bash
chmod 600 .sessions.json .audit.log
```

### 查看日志
```bash
tail -f /tmp/backend.log
```

## 安全建议

1. 使用强密码（12+位，混合字符）
2. 生产环境启用HTTPS
3. 定期检查审计日志
4. 配置日志轮转
5. 监控异常登录
