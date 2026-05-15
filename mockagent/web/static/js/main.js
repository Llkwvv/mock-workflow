
// ====== Global State ======
let allTasks = [];
let currentFilter = 'all';
let currentSearch = '';
let currentUploadedFile = null;
let mainUploadedFile = null;
let taskRefreshInterval = null;
let currentPage = 1;
let lastTasksSignature = '';
const pageSize = 10;

// ====== Initialize ======
document.addEventListener('DOMContentLoaded', () => {
    loadAllTasks();
    loadSampleLists();
    setupMainDragAndDrop();
    setupModalDragAndDrop();
});

// ====== Auto Refresh ======
function startAutoRefresh() {
    if (taskRefreshInterval) return;
    taskRefreshInterval = setInterval(() => {
        loadAllTasks(false);
    }, 5000);
}

function stopAutoRefresh() {
    if (!taskRefreshInterval) return;
    clearInterval(taskRefreshInterval);
    taskRefreshInterval = null;
}

function syncAutoRefresh() {
    const hasActiveTasks = allTasks.some(t => t.status === 'pending' || t.status === 'running');
    if (hasActiveTasks) {
        startAutoRefresh();
    } else {
        stopAutoRefresh();
    }
}

// ====== Main Page File Upload ======
function setupMainDragAndDrop() {
    const mainUpload = document.getElementById('mainFileUpload');
    const mainInput = document.getElementById('mainFileInput');

    mainUpload.addEventListener('click', () => mainInput.click());

    mainUpload.addEventListener('dragover', (e) => {
        e.preventDefault();
        mainUpload.classList.add('dragover');
    });

    mainUpload.addEventListener('dragleave', () => {
        mainUpload.classList.remove('dragover');
    });

    mainUpload.addEventListener('drop', (e) => {
        e.preventDefault();
        mainUpload.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            mainInput.files = e.dataTransfer.files;
            handleMainFileSelect({ target: mainInput });
        }
    });

    mainInput.addEventListener('change', handleMainFileSelect);
}

function handleMainFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!['.csv', '.xls', '.xlsx'].includes(ext)) {
        showToast('不支持的文件格式，请选择 CSV/XLS/XLSX', 'error');
        event.target.value = '';
        return;
    }

    mainUploadedFile = file;
    document.getElementById('mainFileName').textContent = file.name;
    document.getElementById('mainFileSize').textContent = formatFileSize(file.size);
    document.getElementById('mainFileInfo').style.display = 'flex';
    document.getElementById('mainFileUpload').style.display = 'none';
}

function clearMainFile() {
    mainUploadedFile = null;
    document.getElementById('mainFileInput').value = '';
    document.getElementById('mainFileInfo').style.display = 'none';
    document.getElementById('mainFileUpload').style.display = 'flex';
}

// ====== Modal File Upload ======
function setupModalDragAndDrop() {
    const modalUpload = document.getElementById('modalFileUpload');
    const modalInput = document.getElementById('modalFileInput');

    modalUpload.addEventListener('dragover', (e) => {
        e.preventDefault();
        modalUpload.classList.add('dragover');
    });

    modalUpload.addEventListener('dragleave', () => {
        modalUpload.classList.remove('dragover');
    });

    modalUpload.addEventListener('drop', (e) => {
        e.preventDefault();
        modalUpload.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            modalInput.files = e.dataTransfer.files;
            handleModalFileSelect({ target: modalInput });
        }
    });
}

function handleModalFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!['.csv', '.xls', '.xlsx'].includes(ext)) {
        showToast('不支持的文件格式，请选择 CSV/XLS/XLSX', 'error');
        event.target.value = '';
        return;
    }

    currentUploadedFile = file;
    document.getElementById('modalFileName').textContent = file.name;
    document.getElementById('modalFileInfo').style.display = 'flex';
}

function clearFile() {
    currentUploadedFile = null;
    document.getElementById('modalFileInput').value = '';
    document.getElementById('modalFileInfo').style.display = 'none';
}

// ====== Load Sample Lists ======
async function loadSampleLists() {
    try {
        const response = await fetch('/api/samples');
        if (!response.ok) throw new Error('加载样本列表失败');
        const data = await response.json();
        const samples = data.samples || [];

        // Populate quick submit dropdown
        const quickSelect = document.getElementById('quickExistingSample');
        samples.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.path;
            opt.textContent = `${s.name} (${formatFileSize(s.size)})`;
            quickSelect.appendChild(opt);
        });

        // Populate modal dropdown
        const modalSelect = document.getElementById('existingSample');
        samples.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.path;
            opt.textContent = `${s.name} (${formatFileSize(s.size)})`;
            modalSelect.appendChild(opt);
        });
    } catch (e) {
        console.warn('Could not load sample list:', e);
    }
}

// ====== Quick Submit Task ======
async function quickSubmitTask() {
    const btn = document.getElementById('quickSubmitBtn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '提交中...';

    const tableName = document.getElementById('quickTableName').value || 'auto_table';
    const rows = parseInt(document.getElementById('quickRows').value) || 100;

    let filepath = null;

    if (mainUploadedFile) {
        try {
            filepath = await uploadMainFileToServer();
            if (!filepath) throw new Error('文件上传失败');
        } catch (e) {
            btn.disabled = false;
            btn.textContent = originalText;
            showToast(e.message, 'error');
            return;
        }
    } else {
        const existing = document.getElementById('quickExistingSample').value;
        if (existing) {
            filepath = existing;
        } else {
            btn.disabled = false;
            btn.textContent = originalText;
            showToast('请上传文件或选择已有样本', 'error');
            return;
        }
    }

    try {
        const response = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sample_filename: filepath,
                table_name: tableName,
                rows: rows
            })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '创建任务失败');

        showToast('任务创建成功！', 'success');
        clearMainFile();
        document.getElementById('quickExistingSample').value = '';
        startAutoRefresh();
        loadAllTasks();
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

async function uploadMainFileToServer() {
    if (!mainUploadedFile) return null;

    const formData = new FormData();
    formData.append('file', mainUploadedFile);

    const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData
    });

    if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '上传失败');
    }

    const data = await response.json();
    return data.filepath;
}

// ====== Task Management ======
async function loadAllTasks(showToastMsg = false) {
    try {
        const response = await fetch('/api/tasks?limit=200');
        if (!response.ok) throw new Error('加载任务失败');
        const data = await response.json();
        const nextTasks = data.tasks || [];
        const nextSignature = getTasksSignature(nextTasks);
        if (nextSignature === lastTasksSignature && !showToastMsg) {
            syncAutoRefresh();
            return;
        }
        lastTasksSignature = nextSignature;
        allTasks = nextTasks;
        renderTasks();
        renderPagination();
        updateStats();
        renderPreviewPanel();
        syncAutoRefresh();
        if (showToastMsg) showToast('刷新完成', 'success');
    } catch (e) {
        console.error('Failed to load tasks:', e);
        if (showToastMsg) showToast(e.message, 'error');
    }
}

function getFilteredTasks() {
    let filtered = allTasks;
    if (currentFilter !== 'all') {
        filtered = filtered.filter(t => t.status === currentFilter);
    }
    if (currentSearch) {
        const search = currentSearch.toLowerCase();
        filtered = filtered.filter(t =>
            t.sample_filename.toLowerCase().includes(search) ||
            t.table_name.toLowerCase().includes(search)
        );
    }
    return filtered;
}

function renderTasks() {
    const container = document.getElementById('taskList');
    const previousScrollTop = container.scrollTop;
    const filtered = getFilteredTasks();
    const totalPages = Math.ceil(filtered.length / pageSize) || 1;

    if (currentPage > totalPages) currentPage = totalPages;

    const start = (currentPage - 1) * pageSize;
    const pageTasks = filtered.slice(start, start + pageSize);

    if (pageTasks.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📭</div>
                <p>暂无匹配的任务</p>
            </div>
        `;
        return;
    }

    container.innerHTML = pageTasks.map(task => `
        <div class="task-item" data-task-id="${task.id}">
            <div class="task-header">
                <div class="task-info">
                    <div class="task-name">${escapeHtml(task.sample_filename.split('/').pop())}</div>
                    <div class="task-meta">
                        <span>📋 表: ${escapeHtml(task.table_name)}</span>
                        <span>📊 行数: ${task.rows.toLocaleString()}</span>
                        <span>🕐 创建: ${formatTime(task.created_at)}</span>
                        ${task.completed_at ? `<span>✅ 完成: ${formatTime(task.completed_at)}</span>` : ''}
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span class="status-badge status-${task.status}">${getStatusText(task.status)}</span>
                    <div class="task-actions">
                        ${(task.status === 'running' || task.status === 'pending') ? `
                            <button class="btn btn-danger btn-sm" onclick="cancelTask('${task.id}')" title="取消任务">✕ 取消</button>
                        ` : ''}
                        ${task.result_preview ? `
                            <button class="btn btn-primary btn-sm" onclick="openPreview('${task.id}')" title="查看详情">📄 详情</button>
                        ` : ''}
                        ${task.result_full && task.result_full.output_path ? `
                            <button class="btn btn-secondary btn-sm" onclick="downloadResult('${task.result_full.output_path}')" title="下载CSV">⬇ 下载</button>
                        ` : ''}
                    </div>
                </div>
            </div>
            ${(task.status === 'running' || task.status === 'pending') ? `
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${task.progress}%"></div>
                </div>
                <div class="progress-text">处理进度: ${task.progress}%</div>
            ` : ''}
            ${task.error_message ? `<div class="error-msg">❌ 错误: ${escapeHtml(task.error_message)}</div>` : ''}
            ${task.status === 'completed' && task.result_full && task.result_full.generated_rows ? `
                <div class="success-msg">✅ 已生成 ${task.result_full.generated_rows.toLocaleString()} 行数据</div>
            ` : ''}
        </div>
    `).join('');
    container.scrollTop = previousScrollTop;
}

function getTasksSignature(tasks) {
    return JSON.stringify(tasks.map(t => ({
        id: t.id,
        status: t.status,
        progress: t.progress,
        error_message: t.error_message || '',
        completed_at: t.completed_at || '',
        output_path: t.result_full?.output_path || '',
        generated_rows: t.result_full?.generated_rows || 0,
    })));
}

function renderPagination() {
    const container = document.getElementById('pagination');
    const filtered = getFilteredTasks();
    const totalPages = Math.ceil(filtered.length / pageSize) || 1;

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '';
    html += `<button ${currentPage === 1 ? 'disabled' : ''} onclick="goToPage(${currentPage - 1})">‹ 上一页</button>`;

    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
            html += `<button class="${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
        } else if (i === currentPage - 3 || i === currentPage + 3) {
            html += `<span class="pagination-info">...</span>`;
        }
    }

    html += `<button ${currentPage === totalPages ? 'disabled' : ''} onclick="goToPage(${currentPage + 1})">下一页 ›</button>`;
    html += `<span class="pagination-info">共 ${filtered.length} 条，${totalPages} 页</span>`;

    container.innerHTML = html;
}

function goToPage(page) {
    currentPage = page;
    renderTasks();
    renderPagination();
    document.getElementById('taskList').scrollTop = 0;
}

function filterTasks() {
    currentFilter = document.getElementById('statusFilter').value;
    currentSearch = document.getElementById('searchInput').value;
    currentPage = 1;
    renderTasks();
    renderPagination();
}

function updateStats() {
    document.getElementById('stat-total').textContent = allTasks.length;
    document.getElementById('stat-running').textContent = allTasks.filter(t => t.status === 'running').length;
    document.getElementById('stat-completed').textContent = allTasks.filter(t => t.status === 'completed').length;
}

function getStatusText(status) {
    const map = {
        pending: '待处理',
        running: '运行中',
        completed: '已完成',
        failed: '失败',
        cancelled: '已取消'
    };
    return map[status] || status;
}

async function cancelTask(taskId) {
    if (!confirm('确定要取消此任务吗？')) return;
    try {
        const response = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
        if (!response.ok) throw new Error('取消失败');
        showToast('任务已取消', 'warning');
        loadAllTasks();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// ====== Create Task (Modal) ======
function showNewTaskModal() {
    document.getElementById('newTaskModal').classList.add('show');
    clearFile();
    document.getElementById('newTableName').value = 'auto_table';
    document.getElementById('newRows').value = '100';
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('show');
}

async function createTask(event) {
    event.preventDefault();
    const btn = document.getElementById('submitTaskBtn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '提交中...';

    const tableName = document.getElementById('newTableName').value || 'auto_table';
    const rows = parseInt(document.getElementById('newRows').value) || 100;

    let filepath = null;

    if (currentUploadedFile) {
        try {
            filepath = await uploadModalFileToServer();
            if (!filepath) throw new Error('文件上传失败');
        } catch (e) {
            btn.disabled = false;
            btn.textContent = originalText;
            showToast(e.message, 'error');
            return;
        }
    } else {
        const existing = document.getElementById('existingSample').value;
        if (existing) {
            filepath = existing;
        } else {
            btn.disabled = false;
            btn.textContent = originalText;
            showToast('请选择或上传样本文件', 'error');
            return;
        }
    }

    try {
        const response = await fetch('/api/tasks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sample_filename: filepath,
                table_name: tableName,
                rows: rows
            })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '创建任务失败');

        showToast('任务创建成功', 'success');
        closeModal('newTaskModal');
        startAutoRefresh();
        loadAllTasks();
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

async function uploadModalFileToServer() {
    if (!currentUploadedFile) return null;

    const formData = new FormData();
    formData.append('file', currentUploadedFile);

    const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData
    });

    if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '上传失败');
    }

    const data = await response.json();
    return data.filepath;
}

// ====== Preview Panel (10 items) ======
function renderPreviewPanel() {
    const container = document.getElementById('previewContent');
    const countEl = document.getElementById('previewCount');

    // Collect preview rows from completed tasks, most recent first
    const completedTasks = allTasks
        .filter(t => t.status === 'completed' && t.result_preview && t.result_preview.preview_rows && t.result_preview.preview_rows.length > 0)
        .slice(0, 10);

    if (completedTasks.length === 0) {
        countEl.textContent = '0 条数据';
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🔍</div>
                <p>完成生成任务后，数据预览将显示在此处</p>
            </div>
        `;
        return;
    }

    const totalRows = completedTasks.reduce((sum, t) => sum + (t.result_preview.preview_rows?.length || 0), 0);
    countEl.textContent = `${completedTasks.length} 个任务, ${totalRows} 条数据`;

    container.innerHTML = completedTasks.map(task => {
        const rows = task.result_preview.preview_rows || [];
        const cols = rows.length > 0 ? Object.keys(rows[0]) : [];
        const displayRows = rows.slice(0, 5);

        return `
            <div class="preview-item">
                <div class="preview-item-header">
                    <span class="preview-item-source">📄 ${escapeHtml(task.sample_filename.split('/').pop())} → ${escapeHtml(task.table_name)}</span>
                    <span class="preview-item-meta">${task.rows.toLocaleString()} 行 | ${formatTime(task.completed_at)}</span>
                </div>
                <div class="preview-item-table">
                    <table class="preview-table">
                        <thead>
                            <tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr>
                        </thead>
                        <tbody>
                            ${displayRows.map(row => `
                                <tr>${cols.map(c => `<td>${escapeHtml(String(row[c] != null ? row[c] : ''))}</td>`).join('')}</tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
                <div class="preview-item-footer">
                    <span>显示 ${displayRows.length}/${rows.length} 条预览数据</span>
                    <button class="btn btn-primary btn-sm" onclick="openPreview('${task.id}')">📋 查看完整详情</button>
                </div>
            </div>
        `;
    }).join('');
}

// ====== Preview Modal ======
async function openPreview(taskId) {
    try {
        const response = await fetch(`/api/tasks/${taskId}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '获取任务失败');

        const task = data.task;
        if (task.result_preview) {
            showPreviewModal({
                task_id: task.id,
                ...task.result_preview
            }, task.result_full);
        } else if (task.status === 'completed') {
            showPreviewModal({
                preview_rows: [],
                fields: [],
                create_table_sql: 'N/A'
            });
        } else {
            showToast('任务尚未完成或无预览数据', 'warning');
        }
    } catch (e) {
        showToast(e.message, 'error');
    }
}

function showPreviewModal(data, fullData = null) {
    const modal = document.getElementById('previewModal');
    const content = document.getElementById('previewModalContent');

    const rowsHtml = buildPreviewTable(data.preview_rows || []);

    const fieldsHtml = (data.fields || []).map(f => `
        <div class="field-card">
            <div class="field-name">
                <span>${escapeHtml(f.name)}</span>
                ${f.primary_key ? '<span class="badge">PRIMARY</span>' : ''}
            </div>
            <div class="field-type">
                类型: <span class="badge">${escapeHtml(f.type)}</span>
            </div>
            ${f.length ? `<div class="field-detail"><strong>长度:</strong> ${f.length}</div>` : ''}
            ${f.precision ? `<div class="field-detail"><strong>精度:</strong> ${f.precision}</div>` : ''}
            ${f.scale ? `<div class="field-detail"><strong>小数位:</strong> ${f.scale}</div>` : ''}
            ${f.semantic && f.semantic !== 'unknown' ? `<div class="field-detail"><strong>语义:</strong> ${escapeHtml(f.semantic)}</div>` : ''}
            ${f.nullable !== undefined ? `<div class="field-detail"><strong>可空:</strong> ${f.nullable ? '是' : '否'}</div>` : ''}
            ${f.default !== undefined ? `<div class="field-detail"><strong>默认值:</strong> ${escapeHtml(String(f.default))}</div>` : ''}
            ${f.confidence !== undefined && f.confidence !== null ? `<div class="field-detail"><strong>置信度:</strong> ${Math.round(f.confidence * 100)}%</div>` : ''}
            ${f.enum_values && f.enum_values.length ? `<div class="field-detail"><strong>枚举:</strong> ${escapeHtml(f.enum_values.slice(0, 5).join(', '))}${f.enum_values.length > 5 ? '...' : ''}</div>` : ''}
            ${f.value_pool && f.value_pool.length ? `<div class="field-detail"><strong>值池:</strong> ${f.value_pool.length} 个值</div>` : ''}
        </div>
    `).join('');

    const sqlContent = formatSQL(data.create_table_sql || 'N/A');

    content.innerHTML = `
        <div class="preview-tabs">
            <button class="tab-btn active" onclick="switchPreviewTab(event, 'data')">预览数据 (${data.preview_rows?.length || 0})</button>
            <button class="tab-btn" onclick="switchPreviewTab(event, 'fields')">字段信息 (${data.fields?.length || 0})</button>
            <button class="tab-btn" onclick="switchPreviewTab(event, 'sql')">SQL Schema</button>
        </div>
        <div id="tab-data" class="preview-tab-content">
            ${rowsHtml}
            ${fullData && fullData.generated_rows ? `
                <div class="success-msg">
                    ✅ 已生成完整数据: <strong>${fullData.generated_rows.toLocaleString()}</strong> 行
                    ${fullData.output_path ? ` | 保存至: <code>${escapeHtml(fullData.output_path)}</code>` : ''}
                </div>
            ` : ''}
        </div>
        <div id="tab-fields" class="preview-tab-content" style="display:none">
            ${fieldsHtml ? `<div class="fields-grid">${fieldsHtml}</div>` : '<div class="empty-state"><div class="empty-icon">🔍</div><p>无字段信息</p></div>'}
        </div>
        <div id="tab-sql" class="preview-tab-content" style="display:none">
            ${sqlContent}
        </div>
    `;

    modal.classList.add('show');
}

function buildPreviewTable(rows) {
    if (!rows || rows.length === 0) {
        return '<div class="empty-state"><div class="empty-icon">🔍</div><p>无预览数据</p></div>';
    }

    const cols = Object.keys(rows[0]);
    return `
        <div class="preview-table-wrapper">
            <table class="preview-table">
                <thead>
                    <tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr>
                </thead>
                <tbody>
                    ${rows.map(row => `
                        <tr>${cols.map(c => `<td>${escapeHtml(String(row[c] != null ? row[c] : ''))}</td>`).join('')}</tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function formatSQL(sql) {
    if (!sql || sql === 'N/A') {
        return '<div class="empty-state"><div class="empty-icon">📄</div><p>无SQL Schema</p></div>';
    }
    return `<div class="sql-box">${escapeHtml(sql)}</div>`;
}

function switchPreviewTab(event, tabName) {
    document.querySelectorAll('#previewModalContent .tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    if (event && event.target) event.target.classList.add('active');

    document.querySelectorAll('#previewModalContent .preview-tab-content').forEach(content => {
        content.style.display = 'none';
    });
    const tabEl = document.getElementById(`tab-${tabName}`);
    if (tabEl) tabEl.style.display = 'block';
}

// ====== Utilities ======
function refreshAll() {
    loadAllTasks(true);
    loadSampleLists();
}

function refreshPreview() {
    loadAllTasks(true);
}

function downloadResult(path) {
    const filename = path.split('/').pop();
    const link = document.createElement('a');
    link.href = `/output/${filename}`;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast('下载已开始', 'success');
}

function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function formatTime(isoString) {
    if (!isoString) return 'N/A';
    const d = new Date(isoString);
    return d.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
        size /= 1024;
        i++;
    }
    return `${size.toFixed(1)} ${units[i]}`;
}

function calcDuration(start, end) {
    if (!start || !end) return 'N/A';
    const ms = new Date(end) - new Date(start);
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}min`;
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Close modal on outside click
window.onclick = (event) => {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        if (event.target === modal) {
            modal.classList.remove('show');
        }
    });
};
