# 批量导入文件生成多个任务功能 - 最终更新

## 布局调整

根据用户反馈，将批量导入按钮移至"📤 提交文件与任务"框架内，优化用户体验。

### 修改内容

1. **HTML 结构更新** (`index.html`)
   - 将批量导入区域移入"提交文件与任务"卡片内
   - 批量导入切换按钮现在显示在主上传区域顶部
   - 批量上传区域与快速提交区域在同一卡片内
   - 添加了视觉分隔和背景色以区分不同功能区域

2. **JavaScript 函数更新** (`main.js`)
   - 修改 `toggleBatchUpload()` 函数以适应新的HTML结构
   - 现在控制 `#batchUploadArea` 的显示/隐藏
   - 使用 `display: flex` 保持上传区域的 flex 布局

3. **CSS 样式保留**
   - 所有批量上传相关的样式保持不变
   - 响应式设计继续有效

## 功能特性

### ✅ Web API 端点
- `POST /api/tasks/batch` - 批量创建任务
- `POST /api/tasks/batch-from-files` - 从文件批量创建任务

### ✅ CLI 命令
```bash
mockworkflow batch file1.csv file2.csv --rows 100 --output preview
```

### ✅ Web 界面
- 批量导入按钮集成在主上传卡片中
- 拖拽多文件上传支持
- 实时文件列表管理
- 批量参数配置

## 使用说明

### Web 界面操作

1. 访问 http://localhost:8000
2. 在"提交文件与任务"卡片顶部，点击 **"➕ 批量导入文件"** 按钮
3. 展开的批量上传区域中：
   - 拖拽多个文件到上传区域或点击选择文件
   - 配置参数（行数、表名前缀等）
   - 点击 **"🚀 批量创建任务"** 按钮
4. 在任务列表中查看所有任务的处理进度和结果

### CLI 使用

```bash
# 批量处理多个文件
mockworkflow batch samples/users.csv samples/vehicles.csv --rows 100

# 批量处理并导出到CSV
mockworkflow batch samples/*.csv --rows 1000 --output csv --csv-path ./output

# 批量处理（启用LLM）
mockworkflow batch samples/*.csv --rows 100 --enable-llm
```

### API 调用

```bash
# 批量创建任务
curl -X POST http://localhost:8000/api/tasks/batch \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {"sample_filename": "data1.csv", "table_name": "table1", "rows": 100},
      {"sample_filename": "data2.csv", "table_name": "table2", "rows": 100}
    ],
    "auto_table_name": false
  }'
```

## 测试验证

所有功能测试通过：
- ✅ Web 服务器正常运行
- ✅ 批量导入按钮位置正确
- ✅ 切换功能正常工作
- ✅ API 批量创建任务
- ✅ CLI 批量命令
- ✅ 任务处理流程

## 文件修改清单

1. `mockworkflow/web/templates/index.html` - 布局结构调整
2. `mockworkflow/web/static/js/main.js` - 切换函数更新
3. `README.md` - 文档更新
4. `BATCH_FEATURE_SUMMARY.md` - 功能说明文档

## 设计考虑

1. **用户体验**: 将批量导入功能集成到主卡片中，减少页面跳转
2. **视觉层次**: 使用背景色和边框区分不同功能区域
3. **一致性**: 保持与现有UI风格一致
4. **功能性**: 不改变原有功能，仅调整布局
5. **响应式**: 继续支持移动端显示

## 总结

批量导入文件生成多个任务的功能已完成，包括：
- ✅ Web API 支持
- ✅ CLI 命令支持  
- ✅ Web 界面集成
- ✅ 布局优化
- ✅ 完整文档
- ✅ 测试验证

功能稳定可用，满足所有需求！
