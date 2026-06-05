
// ====== Global State ======
let allTasks = [];
let currentFilter = 'all';
let currentSearch = '';
let currentUploadedFile = null;
let mainUploadedFile = null;
let taskRefreshInterval = null;
let currentPage = 1;
let lastTasksSignature = '';
let batchFiles = [];
const pageSize = 10;
let charts = {};  // Store Chart instances for destroy/recreate
let ws = null;  // WebSocket connection
let wsReconnectTimer = null;  // Reconnection timer

// ====== Initialize ======
document.addEventListener('DOMContentLoaded', () => {
    loadAllTasks();
    loadSampleLists();
    loadStatistics();
    loadSchedules();
    setupMainDragAndDrop();
    setupModalDragAndDrop();
    connectWebSocket();  // Try WebSocket first
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

// ====== Statistics Charts ======
async function loadStatistics() {
    try {
        const response = await fetch('/api/tasks/stats/summary');
        if (!response.ok) throw new Error('加载统计失败');
        const data = await response.json();

        // Update summary values
        const totalEl = document.getElementById('stats-total');
        if (totalEl) totalEl.textContent = data.total_tasks;

        const successRateEl = document.getElementById('stats-success-rate');
        if (successRateEl) successRateEl.textContent = data.success_rate + '%';

        const avgRowsEl = document.getElementById('stats-avg-rows');
        if (avgRowsEl) avgRowsEl.textContent = data.avg_rows;

        const totalRowsEl = document.getElementById('stats-total-rows');
        if (totalRowsEl) totalRowsEl.textContent = data.total_rows_generated.toLocaleString();

        const avgTimeEl = document.getElementById('stats-avg-time');
        if (avgTimeEl) avgTimeEl.textContent = data.avg_completion_time + 's';

        // Destroy old charts
        Object.values(charts).forEach(c => c.destroy());
        charts = {};

        // Status distribution chart (Doughnut)
        charts.status = new Chart(document.getElementById('statusChart'), {
            type: 'doughnut',
            data: {
                labels: ['待处理', '运行中', '已完成', '失败', '已取消'],
                datasets: [{
                    data: [
                        data.status_distribution.pending,
                        data.status_distribution.running,
                        data.status_distribution.completed,
                        data.status_distribution.failed,
                        data.status_distribution.cancelled,
                    ],
                    backgroundColor: ['#94a3b8', '#2563eb', '#059669', '#dc2626', '#d97706'],
                }]
            },
            options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
        });

        // Daily trend chart (Line)
        charts.daily = new Chart(document.getElementById('dailyChart'), {
            type: 'line',
            data: {
                labels: data.daily_counts.map(d => d.date.slice(5)),  // MM-DD
                datasets: [{
                    label: '任务数',
                    data: data.daily_counts.map(d => d.count),
                    borderColor: '#2563eb', backgroundColor: '#dbeafe',
                    fill: true, tension: 0.3,
                }]
            },
            options: { responsive: true, scales: { y: { beginAtZero: true } } }
        });

        // Hot tables chart (Bar)
        charts.table = new Chart(document.getElementById('tableChart'), {
            type: 'bar',
            data: {
                labels: data.top_tables.map(t => t.name),
                datasets: [{
                    label: '任务数',
                    data: data.top_tables.map(t => t.count),
                    backgroundColor: '#06b6d4',
                }]
            },
            options: { responsive: true, scales: { y: { beginAtZero: true } } }
        });
    } catch (e) {
        console.error('Statistics load failed:', e);
    }
}

// ====== WebSocket Real-time Updates ======
function connectWebSocket() {
    if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
    }

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws/tasks`);

    ws.onopen = () => {
        console.log('WebSocket connected');
        stopAutoRefresh();  // Stop polling when WebSocket is connected
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.event === 'task_updated' || data.event === 'task_created') {
            // Update local allTasks
            const idx = allTasks.findIndex(t => t.id === data.task.id);
            if (idx >= 0) {
                allTasks[idx] = data.task;
            } else {
                allTasks.unshift(data.task);
            }
            renderTasks();
            renderPagination();
            updateStats();
            loadStatistics();
            renderPreviewPanel();
        }
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected');
        ws = null;
        // Start polling fallback and auto reconnect
        startAutoRefresh();
        wsReconnectTimer = setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        ws.close();
    };
}

// ====== Unified File Upload ======
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
            handleFileSelect({ target: mainInput });
        }
    });

    mainInput.addEventListener('change', handleFileSelect);
}

function handleFileSelect(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    // Check file types
    const allowedExts = ['.csv', '.xls', '.xlsx'];
    for (const file of files) {
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        if (!allowedExts.includes(ext)) {
            showToast(`不支持的文件格式: ${file.name}`, 'error');
            event.target.value = '';
            return;
        }
    }

    if (files.length === 1) {
        // Single file mode
        handleSingleFile(files[0]);
    } else {
        // Batch mode
        handleBatchFiles(files);
    }
}

function updateSubmitButton(text) {
    // Wait for DOM to be ready
    return new Promise((resolve) => {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                const btn = document.getElementById('submitBtn');
                if (btn) {
                    btn.innerHTML = text;
                    btn.dataset.originalHtml = text;
                    resolve();
                } else {
                    // Try again after a short delay
                    setTimeout(() => {
                        const retryBtn = document.getElementById('submitBtn');
                        if (retryBtn) {
                            retryBtn.innerHTML = text;
                            retryBtn.dataset.originalHtml = text;
                            resolve();
                        } else {
                            console.warn('Submit button still not found after 1 second');
                            resolve();
                        }
                    }, 1000);
                }
            });
        } else {
            const btn = document.getElementById('submitBtn');
            if (btn) {
                btn.innerHTML = text;
                btn.dataset.originalHtml = text;
                resolve();
            } else {
                // Try again after a short delay
                setTimeout(() => {
                    const retryBtn = document.getElementById('submitBtn');
                    if (retryBtn) {
                        retryBtn.innerHTML = text;
                        retryBtn.dataset.originalHtml = text;
                        resolve();
                    } else {
                        console.warn('Submit button still not found after 1 second');
                        resolve();
                    }
                }, 1000);
            }
        }
    });
}

function handleSingleFile(file) {
    mainUploadedFile = file;
    batchFiles = [];

    const fileNameEl = document.getElementById('mainFileName');
    if (fileNameEl) fileNameEl.textContent = file.name;

    const fileSizeEl = document.getElementById('mainFileSize');
    if (fileSizeEl) fileSizeEl.textContent = formatFileSize(file.size);

    const mainFileInfoEl = document.getElementById('mainFileInfo');
    if (mainFileInfoEl) mainFileInfoEl.style.display = 'flex';

    const batchFileInfoEl = document.getElementById('batchFileInfo');
    if (batchFileInfoEl) batchFileInfoEl.style.display = 'none';

    const mainFileUploadEl = document.getElementById('mainFileUpload');
    if (mainFileUploadEl) mainFileUploadEl.style.display = 'none';

    const batchOptionsGroupEl = document.getElementById('batchOptionsGroup');
    if (batchOptionsGroupEl) batchOptionsGroupEl.style.display = 'none';

    // 表名由后端根据文件名自动生成，前端不再展示/猜测

    // Update hint
    const hint = document.getElementById('uploadModeHint');
    if (hint) {
        hint.textContent = '单文件模式';
        hint.className = 'upload-mode-hint mode-single';
    }

    // Update button - use our safe function
    updateSubmitButton('🚀 提交生成任务');
}

function handleBatchFiles(files) {
    mainUploadedFile = null;
    batchFiles = Array.from(files).slice(0, 100);  // Max 100 files

    document.getElementById('mainFileInfo').style.display = 'none';
    document.getElementById('batchFileInfo').style.display = 'block';
    document.getElementById('mainFileUpload').style.display = 'none';
    document.getElementById('batchOptionsGroup').style.display = 'block';

    // Render batch files
    renderBatchFiles();

    // Update hint
    const hint = document.getElementById('uploadModeHint');
    hint.textContent = `批量模式 (${batchFiles.length} 个文件)`;
    hint.className = 'upload-mode-hint mode-batch';

    // Update button
    document.getElementById('submitBtn').innerHTML = `🚀 批量创建任务 (${batchFiles.length} 个)`;
}

function clearMainFile() {
    mainUploadedFile = null;
    batchFiles = [];

    const mainFileInputEl = document.getElementById('mainFileInput');
    if (mainFileInputEl) mainFileInputEl.value = '';

    const mainFileInfoEl = document.getElementById('mainFileInfo');
    if (mainFileInfoEl) mainFileInfoEl.style.display = 'none';

    const batchFileInfoEl = document.getElementById('batchFileInfo');
    if (batchFileInfoEl) batchFileInfoEl.style.display = 'none';

    const mainFileUploadEl = document.getElementById('mainFileUpload');
    if (mainFileUploadEl) mainFileUploadEl.style.display = 'flex';

    const batchOptionsGroupEl = document.getElementById('batchOptionsGroup');
    if (batchOptionsGroupEl) batchOptionsGroupEl.style.display = 'none';

    const hint = document.getElementById('uploadModeHint');
    if (hint) {
        hint.textContent = '拖入文件自动识别';
        hint.className = 'upload-mode-hint';
    }

    // Update button - use our safe function
    updateSubmitButton('🚀 提交生成任务');
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

        // Populate modal dropdown (only if element exists)
        const modalSelect = document.getElementById('existingSample');
        if (modalSelect) {
            samples.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.path;
                opt.textContent = `${s.name} (${formatFileSize(s.size)})`;
                opt.dataset.filename = s.name.replace(/\.[^/.]+$/, '');
                modalSelect.appendChild(opt);
            });

        }
    } catch (e) {
        console.warn('Could not load sample list:', e);
    }
}

// ====== Unified Submit Task ======
async function submitTask() {
    console.log('submitTask called', { mainUploadedFile, batchFiles: batchFiles.length });

    // Get the button and save original HTML BEFORE changing it
    const btn = document.getElementById('submitBtn');
    if (!btn) {
        console.error('Submit button not found');
        return;
    }
    const originalHtml = btn.innerHTML;

    // Use our safe function to update button
    await updateSubmitButton('提交中...');

    btn.disabled = true;

    try {
        // 表名统一交由后端按文件名自动生成
        const tableName = 'auto_table';
        const rows = parseInt(document.getElementById('quickRows').value) || 100;
        const enableDbExport = document.getElementById('quickEnableDbExport').checked;
        const isBatch = batchFiles.length > 1;

        if (isBatch) {
            // Batch mode: upload multiple files
            const formData = new FormData();
            batchFiles.forEach(file => {
                formData.append('files', file);
            });
            formData.append('rows', rows);
            formData.append('enable_db_export', enableDbExport);
            const tablePrefix = document.getElementById('batchTablePrefix').value || '';
            formData.append('table_prefix', tablePrefix);

            const response = await fetch('/api/tasks/batch-from-files', {
                method: 'POST',
                body: formData
            });

            const text = await response.text();
            let data;
            try {
                data = JSON.parse(text);
            } catch {
                throw new Error(text || '批量创建任务失败');
            }
            if (!response.ok) throw new Error(data.detail || '批量创建任务失败');
            showToast(`成功创建 ${data.created_count || data.task_ids?.length || 1} 个任务！`, 'success');
            clearMainFile();
        } else {
            // Single file mode
            let filepath = null;

            if (mainUploadedFile) {
                // Check if it's a server file path or a local File object
                if (mainUploadedFile.path) {
                    // Server sample file, use path directly
                    filepath = mainUploadedFile.path;
                } else {
                    // Local file, upload to server
                    filepath = await uploadFileToServer(mainUploadedFile);
                    if (!filepath) throw new Error('文件上传失败');
                }
            } else {
                showToast('请上传文件', 'error');
                // Restore original button state
                updateSubmitButton(originalHtml);
                return;
            }

            const response = await fetch('/api/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sample_filename: filepath,
                    table_name: tableName,
                    rows: rows,
                    enable_db_export: enableDbExport
                })
            });

            const text = await response.text();
            let data;
            try {
                data = JSON.parse(text);
            } catch {
                throw new Error(text || '创建任务失败');
            }
            if (!response.ok) throw new Error(data.detail || '创建任务失败');
            showToast('任务创建成功！', 'success');
            // Don't clear file after successful submission, user might want to create more tasks
            // clearMainFile();
        }

        startAutoRefresh();
        loadAllTasks();
    } catch (e) {
        console.error('Submit task error:', e);
        showToast(e.message || '提交失败，请检查控制台', 'error');
    } finally {
        // Always restore button state
        updateSubmitButton(originalHtml);
        btn.disabled = false;
    }
}

async function uploadFileToServer(file) {
    const formData = new FormData();
    formData.append('file', file);

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
        loadStatistics();
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
            ${task.schema_mismatch && task.retryable ? `
                <div class="schema-mismatch-action">
                    <button class="btn btn-warning btn-sm" onclick="retryTask('${task.id}')" title="重建表并重试">🔄 重建表并重试</button>
                </div>
            ` : ''}
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
    const totalEl = document.getElementById('stat-total');
    if (totalEl) totalEl.textContent = allTasks.length;

    const runningEl = document.getElementById('stat-running');
    if (runningEl) runningEl.textContent = allTasks.filter(t => t.status === 'running').length;

    const completedEl = document.getElementById('stat-completed');
    if (completedEl) completedEl.textContent = allTasks.filter(t => t.status === 'completed').length;
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

async function retryTask(taskId) {
    if (!confirm('确定要重建表并重试此任务吗？这将删除现有表数据。')) return;
    try {
        const response = await fetch(`/api/tasks/${taskId}/retry`, { method: 'POST' });
        if (!response.ok) throw new Error('重试失败');
        showToast('任务已重新提交', 'success');
        loadAllTasks();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// ====== Create Task (Modal) ======
function showNewTaskModal() {
    document.getElementById('newTaskModal').classList.add('show');
    clearFile();
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

    // 表名统一交由后端按文件名自动生成
    const tableName = 'auto_table';
    const rows = parseInt(document.getElementById('newRows').value) || 100;
    const enableDbExport = document.getElementById('newEnableDbExport')?.checked ?? true;

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
                rows: rows,
                enable_db_export: enableDbExport
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
    if (countEl) {
        countEl.textContent = `${completedTasks.length} 个任务, ${totalRows} 条数据`;
    }

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

// ====== Batch File Functions ======
function handleBatchFileSelect(files) {
    const allowedExtensions = ['.csv', '.xls', '.xlsx'];
    let addedCount = 0;

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();

        if (!allowedExtensions.includes(ext)) {
            continue;
        }

        // Check for duplicates
        if (batchFiles.some(f => f.name === file.name && f.size === file.size)) {
            continue;
        }

        // Check limit
        if (batchFiles.length >= 100) {
            showToast('最多只能添加100个文件', 'warning');
            break;
        }

        batchFiles.push(file);
        addedCount++;
    }

    if (addedCount > 0) {
        renderBatchFiles();
        updateBatchStats();
        showToast(`已添加 ${addedCount} 个文件`, 'success');
    }
}

function renderBatchFiles() {
    const list = document.getElementById('batchFilesList');
    const info = document.getElementById('batchFileInfo');

    if (batchFiles.length === 0) {
        info.style.display = 'none';
        return;
    }

    info.style.display = 'block';

    list.innerHTML = batchFiles.map((file, index) => `
        <div class="batch-file-item">
            <span class="file-icon">📄</span>
            <span class="file-name">${escapeHtml(file.name)}</span>
            <span class="file-size">${formatFileSize(file.size)}</span>
            <button class="remove-file" onclick="removeBatchFile(${index})" title="移除">✕</button>
        </div>
    `).join('');

    updateBatchFileCount();
}

function updateBatchFiles() {
    const uploadCard = document.getElementById('batchUploadCard');
    if (batchFiles.length > 0) {
        uploadCard.classList.add('has-files');
    } else {
        uploadCard.classList.remove('has-files');
    }
}

function removeBatchFile(index) {
    batchFiles.splice(index, 1);
    renderBatchFiles();
    showToast('文件已移除', 'info');
}

function clearBatchFiles() {
    if (batchFiles.length === 0) return;
    if (!confirm(`确定要清空 ${batchFiles.length} 个文件吗？`)) return;
    clearMainFile();
    showToast('已清空所有文件', 'info');
}

function updateBatchStats() {
    // No specific stats needed, handled by render
}

function updateBatchFileCount() {
    // Handled by unified submit button
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

// ====== Scheduled Tasks ======
let allSchedules = [];

async function loadSchedules() {
    try {
        const response = await fetch('/api/schedules');
        if (!response.ok) throw new Error('加载定时任务失败');
        const data = await response.json();
        allSchedules = data.schedules || [];
        renderSchedules();
    } catch (e) {
        console.error('Load schedules failed:', e);
        showToast('加载定时任务失败', 'error');
    }
}

function renderSchedules() {
    const list = document.getElementById('scheduleList');
    if (!list) return;

    if (allSchedules.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⏰</div>
                <p>暂无定时任务</p>
            </div>
        `;
        return;
    }

    list.innerHTML = allSchedules.map(schedule => `
        <div class="schedule-item ${schedule.enabled ? '' : 'disabled'}">
            <div class="schedule-info">
                <div class="schedule-name">${escapeHtml(schedule.sample_filename)}</div>
                <div class="schedule-meta">
                    <span>📋 表: ${escapeHtml(schedule.table_name)}</span>
                    <span>📊 行数: ${schedule.rows}</span>
                    <span>⏰ Cron: ${escapeHtml(schedule.cron)}</span>
                    <span>🕐 下次: ${schedule.next_run ? new Date(schedule.next_run).toLocaleString() : '计算中'}</span>
                </div>
            </div>
            <div class="schedule-actions">
                <button class="btn btn-sm ${schedule.enabled ? 'btn-warning' : 'btn-success'}" onclick="toggleSchedule('${schedule.id}')" title="${schedule.enabled ? '禁用' : '启用'}">
                    ${schedule.enabled ? '⏸ 禁用' : '▶ 启用'}
                </button>
                <button class="btn btn-sm btn-danger" onclick="deleteSchedule('${schedule.id}')" title="删除">🗑 删除</button>
            </div>
        </div>
    `).join('');
}

async function showScheduleModal() {
    await loadSamples();
    document.getElementById('scheduleModal').classList.add('show');
}

async function createSchedule(event) {
    event.preventDefault();
    const sample = document.getElementById('scheduleSample').value;
    const tableName = document.getElementById('scheduleTableName').value;
    const rows = parseInt(document.getElementById('scheduleRows').value);
    const cron = document.getElementById('scheduleCron').value;
    const enableDbExport = document.getElementById('scheduleEnableDbExport').checked;

    if (!sample || !tableName || !cron) {
        showToast('请填写所有必填项', 'error');
        return;
    }

    try {
        const response = await fetch('/api/schedules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sample_filename: sample,
                table_name: tableName,
                rows: rows,
                cron: cron,
                enable_db_export: enableDbExport
            })
        });

        if (!response.ok) throw new Error('创建定时任务失败');

        showToast('定时任务创建成功', 'success');
        closeModal('scheduleModal');
        loadSchedules();
    } catch (e) {
        console.error('Create schedule failed:', e);
        showToast(e.message || '创建定时任务失败', 'error');
    }
}

async function toggleSchedule(scheduleId) {
    try {
        const response = await fetch(`/api/schedules/${scheduleId}/toggle`, { method: 'PATCH' });
        if (!response.ok) throw new Error('切换状态失败');
        showToast('定时任务状态已更新', 'success');
        loadSchedules();
    } catch (e) {
        console.error('Toggle schedule failed:', e);
        showToast(e.message || '切换状态失败', 'error');
    }
}

async function deleteSchedule(scheduleId) {
    if (!confirm('确定要删除此定时任务吗？')) return;

    try {
        const response = await fetch(`/api/schedules/${scheduleId}`, { method: 'DELETE' });
        if (!response.ok) throw new Error('删除定时任务失败');
        showToast('定时任务已删除', 'success');
        loadSchedules();
    } catch (e) {
        console.error('Delete schedule failed:', e);
        showToast(e.message || '删除定时任务失败', 'error');
    }
}

async function loadSamples() {
    try {
        const response = await fetch('/api/samples');
        if (!response.ok) throw new Error('加载样本文件失败');
        const data = await response.json();
        const samples = data.samples || [];

        // Update sample list
        const sampleList = document.getElementById('sampleList');
        if (sampleList) {
            if (samples.length === 0) {
                sampleList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon">📁</div>
                        <p>暂无样本文件</p>
                    </div>
                `;
            } else {
                sampleList.innerHTML = samples.map(sample => `
                    <div class="sample-item">
                        <div class="sample-info">
                            <div class="sample-name">${escapeHtml(sample.name)}</div>
                            <div class="sample-meta">
                                <span>📊 大小: ${formatFileSize(sample.size)}</span>
                                <span>🕐 修改: ${new Date(sample.modified).toLocaleString()}</span>
                            </div>
                        </div>
                        <div class="sample-actions">
                            <button class="btn btn-sm btn-primary" onclick="useSample('${sample.path}', '${escapeHtml(sample.name)}')" title="使用此文件">📋 使用</button>
                        </div>
                    </div>
                `).join('');
            }
        }

        // Update dropdowns
        const scheduleSelect = document.getElementById('scheduleSample');
        const existingSelect = document.getElementById('existingSample');

        if (scheduleSelect) {
            scheduleSelect.innerHTML = '<option value="">-- 选择样本文件 --</option>' +
                samples.map(s => `<option value="${s.path}">${escapeHtml(s.name)}</option>`).join('');
        }

        if (existingSelect) {
            existingSelect.innerHTML = '<option value="">-- 选择现有样本文件 --</option>' +
                samples.map(s => `<option value="${s.path}">${escapeHtml(s.name)}</option>`).join('');
        }
    } catch (e) {
        console.error('Load samples failed:', e);
    }
}

function showUploadModal() {
    document.getElementById('uploadModal').classList.add('show');
}

function handleUploadFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    const fileName = document.getElementById('uploadFileName');
    const fileInfo = document.getElementById('uploadFileInfo');
    
    fileName.textContent = file.name;
    fileInfo.style.display = 'block';
}

function clearUploadFile() {
    const input = document.getElementById('uploadFileInput');
    const fileInfo = document.getElementById('uploadFileInfo');
    
    input.value = '';
    fileInfo.style.display = 'none';
}

async function uploadSampleFile(event) {
    event.preventDefault();
    
    const input = document.getElementById('uploadFileInput');
    const file = input.files[0];
    
    if (!file) {
        showToast('请选择文件', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    const btn = document.getElementById('uploadBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '上传中...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const text = await response.text();
        let data;
        try {
            data = JSON.parse(text);
        } catch {
            throw new Error(text || '上传失败');
        }

        if (!response.ok) throw new Error(data.detail || '上传失败');

        showToast('文件上传成功', 'success');
        closeModal('uploadModal');
        loadSamples();
        
        // Reset form
        input.value = '';
        document.getElementById('uploadFileInfo').style.display = 'none';
    } catch (e) {
        console.error('Upload failed:', e);
        showToast(e.message || '上传失败', 'error');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

function useSample(path, name) {
    // Set the file in the main upload area
    const mainFileInfo = document.getElementById('mainFileInfo');
    const mainFileName = document.getElementById('mainFileName');
    const mainFileUpload = document.getElementById('mainFileUpload');
    
    mainFileName.textContent = name;
    mainFileInfo.style.display = 'block';
    mainFileUpload.style.display = 'none';
    
    // Store the sample path for later use
    mainUploadedFile = { path, name };
    
    showToast(`已选择样本文件: ${name}`, 'success');
}
