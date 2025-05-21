/**
 * 文件服务器前端交互脚本
 * 用于支持网盘系统的文件浏览、上传、下载等操作
 */

// 全局变量
let selectedFiles = new Set();
let currentSessionId = null;
let dragCounter = 0;

/**
 * 根据文件扩展名判断文件类型，返回对应的图标类
 * @param {string} filename - 文件名
 * @returns {string} - 图标CSS类名
 */
function getFileIconClass(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    
    // 图片文件
    if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'].includes(ext)) {
        return 'image';
    }
    
    // 视频文件
    if (['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm'].includes(ext)) {
        return 'video';
    }
    
    // 压缩文件
    if (['zip', 'rar', '7z', 'tar', 'gz', 'bz2'].includes(ext)) {
        return 'archive';
    }
    
    // 文档文件
    if (['doc', 'docx', 'pdf', 'txt', 'rtf', 'md', 'ppt', 'pptx', 'xls', 'xlsx'].includes(ext)) {
        return 'document';
    }
    
    // 音频文件
    if (['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac'].includes(ext)) {
        return 'audio';
    }
    
    // 代码文件
    if (['js', 'py', 'java', 'c', 'cpp', 'cs', 'html', 'css', 'php', 'rb', 'go', 'ts'].includes(ext)) {
        return 'code';
    }
    
    // 默认文件图标
    return '';
}

// 初始化路径导航
function initPathNavigation(pathParts) {
    const pathPartsElement = document.getElementById('path-parts');
    let html = '';
    
    pathParts.forEach((part, index) => {
        html += `<span class="separator">/</span><a href="/browse/${part.path}">${part.name}</a>`;
    });
    
    pathPartsElement.innerHTML = html;
}

// 渲染文件列表
function renderFileList(items) {
    console.log('Rendering file list with items:', items);
    const fileListElement = document.getElementById('file-list');
    if (!fileListElement) {
        console.error('File list element not found in DOM');
        return;
    }
    
    let html = '';
    
    // 如果不是根目录，添加返回上级目录选项
    if (currentPath) {
        const parentPath = currentPath.split('/').slice(0, -1).join('/');
        html += `
            <tr class="parent-dir">
                <td></td>
                <td colspan="4">
                    <a href="/browse/${parentPath}">
                        <span class="folder-icon"></span> ../ (返回上级目录)
                    </a>
                </td>
            </tr>
        `;
    }
    
    try {
        // 确保 items 是数组
        if (!Array.isArray(items)) {
            console.error('Items is not an array:', items);
            items = [];
        }
        
        // 先显示文件夹，再显示文件
        const folders = items.filter(item => item && item.is_dir).sort((a, b) => a.name.localeCompare(b.name));
        const files = items.filter(item => item && !item.is_dir).sort((a, b) => a.name.localeCompare(b.name));
        
        console.log('Folders to render:', folders.length);
        console.log('Files to render:', files.length);
        
        // 渲染文件夹
        folders.forEach(folder => {
            const folderPath = currentPath ? currentPath + '/' + folder.name : folder.name;
            html += `
                <tr data-path="${folderPath}" data-type="folder">
                    <td></td>
                    <td>
                        <a href="/browse/${folderPath}" class="item-name">
                            <span class="folder-icon"></span> ${folder.name}
                        </a>
                    </td>
                    <td>文件夹</td>
                    <td>${folder.mtime_str}</td>
                    <td>
                        <button class="action-btn upload-to-folder" data-path="${folderPath}" title="上传到此文件夹">
                            <i class="icon-upload"></i>
                        </button>
                    </td>
                </tr>
            `;
        });
        
        // 渲染文件
        files.forEach(file => {
            const filePath = currentPath ? currentPath + '/' + file.name : file.name;
            const fileSize = formatFileSize(file.size);
            const fileIconClass = getFileIconClass(file.name);
            
            html += `
                <tr data-path="${filePath}" data-type="file">
                    <td><input type="checkbox" class="file-checkbox" data-path="${filePath}"></td>
                    <td>
                        <span class="item-name">
                            <span class="file-icon ${fileIconClass}"></span> ${file.name}
                        </span>
                    </td>
                    <td>${fileSize}</td>
                    <td>${file.mtime_str}</td>
                    <td>
                        <a href="/download/${filePath}" class="action-btn download-file" download title="下载">
                            <i class="icon-download"></i>
                        </a>
                    </td>
                </tr>
            `;
        });
    } catch (error) {
        console.error('Error rendering file list:', error);
        html += `
            <tr>
                <td colspan="5">文件列表渲染错误: ${error.message}</td>
            </tr>
        `;
    }
    
    // 如果没有文件，显示一条提示
    if (html === '') {
        html = `
            <tr>
                <td colspan="5" class="empty-message">没有文件或目录</td>
            </tr>
        `;
    }
    
    fileListElement.innerHTML = html;
    console.log('File list rendering completed');
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    
    return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + units[i];
}

// 初始化事件监听
function initEventListeners() {
    // 全选/取消全选
    const selectAllCheckbox = document.getElementById('select-all');
    selectAllCheckbox.addEventListener('change', function() {
        const fileCheckboxes = document.querySelectorAll('.file-checkbox');
        fileCheckboxes.forEach(checkbox => {
            checkbox.checked = selectAllCheckbox.checked;
            
            if (selectAllCheckbox.checked) {
                selectedFiles.add(checkbox.dataset.path);
            } else {
                selectedFiles.delete(checkbox.dataset.path);
            }
        });
        
        updateDownloadButtonState();
    });
    
    // 文件复选框
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('file-checkbox')) {
            const filePath = e.target.dataset.path;
            
            if (e.target.checked) {
                selectedFiles.add(filePath);
            } else {
                selectedFiles.delete(filePath);
                selectAllCheckbox.checked = false;
            }
            
            updateDownloadButtonState();
        }
    });
    
    // 下载选中按钮
    const downloadSelectedBtn = document.getElementById('download-selected-btn');
    downloadSelectedBtn.addEventListener('click', function() {
        if (selectedFiles.size > 0) {
            queueDownloads(Array.from(selectedFiles));
        }
    });
    
    // 上传按钮
    const uploadBtn = document.getElementById('upload-btn');
    const fileInput = document.getElementById('file-input');
    
    uploadBtn.addEventListener('click', function() {
        fileInput.click();
    });
    
    fileInput.addEventListener('change', function() {
        if (fileInput.files.length > 0) {
            uploadFiles(fileInput.files, currentPath);
            // 清空input，以便再次选择相同文件时触发change事件
            fileInput.value = '';
        }
    });
    
    // 上传到文件夹按钮
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('upload-to-folder') || e.target.closest('.upload-to-folder')) {
            const targetButton = e.target.classList.contains('upload-to-folder') ? 
                e.target : e.target.closest('.upload-to-folder');
            const targetPath = targetButton.dataset.path;
            const tempFileInput = document.createElement('input');
            tempFileInput.type = 'file';
            tempFileInput.multiple = true;
            
            tempFileInput.addEventListener('change', function() {
                if (tempFileInput.files.length > 0) {
                    uploadFiles(tempFileInput.files, targetPath);
                }
            });
            
            tempFileInput.click();
        }
    });
    
    // 模态对话框关闭按钮
    const closeModalBtn = document.querySelector('.modal .close');
    closeModalBtn.addEventListener('click', function() {
        closeModal();
    });
    
    // 模态对话框取消按钮
    const modalCancelBtn = document.getElementById('modal-cancel');
    modalCancelBtn.addEventListener('click', function() {
        closeModal();
    });
    
    // 文件拖放上传
    const dropZone = document.querySelector('.file-list-container');
    
    // 处理拖拽进入事件
    dropZone.addEventListener('dragenter', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dragCounter++;
        dropZone.classList.add('drag-over');
    });
    
    // 处理拖拽离开事件
    dropZone.addEventListener('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dragCounter--;
        if (dragCounter === 0) {
            dropZone.classList.remove('drag-over');
        }
    });
    
    // 处理拖拽悬停事件
    dropZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
    });
    
    // 处理放置事件
    dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dragCounter = 0;
        dropZone.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            uploadFiles(files, currentPath);
        }
    });
    
    // 双击行为 - 文件下载/文件夹导航
    document.addEventListener('dblclick', function(e) {
        const row = e.target.closest('tr');
        if (row && row.dataset.path) {
            const type = row.dataset.type;
            const path = row.dataset.path;
            
            if (type === 'file') {
                window.location.href = `/download/${path}`;
            } else if (type === 'folder') {
                window.location.href = `/browse/${path}`;
            }
        }
    });
}

// 更新下载按钮状态
function updateDownloadButtonState() {
    const downloadSelectedBtn = document.getElementById('download-selected-btn');
    downloadSelectedBtn.disabled = selectedFiles.size === 0;
}

// 初始化上下文菜单
function initContextMenu() {
    const contextMenu = document.getElementById('context-menu');
    
    // 准备上下文菜单的HTML结构
    contextMenu.innerHTML = `
        <ul>
            <li id="context-refresh"><i class="icon-refresh"></i> 刷新</li>
            <li class="separator"></li>
            <li id="context-download" class="file-only"><i class="icon-download"></i> 下载文件</li>
            <li id="context-upload" class="folder-only"><i class="icon-upload"></i> 上传到此处</li>
            <li id="context-download-all" class="folder-only"><i class="icon-download-all"></i> 下载整个文件夹</li>
        </ul>
    `;
    
    const contextRefresh = document.getElementById('context-refresh');
    const contextDownload = document.getElementById('context-download');
    const contextUpload = document.getElementById('context-upload');
    const contextDownloadAll = document.getElementById('context-download-all');
    
    // 显示上下文菜单
    document.addEventListener('contextmenu', function(e) {
        const target = e.target.closest('tr');
        
        if (target && (target.dataset.type === 'file' || target.dataset.type === 'folder')) {
            e.preventDefault();
            
            // 设置菜单位置，避免超出窗口边界
            const x = Math.min(e.clientX, window.innerWidth - 200);
            const y = Math.min(e.clientY, window.innerHeight - 200);
            
            contextMenu.style.left = `${x}px`;
            contextMenu.style.top = `${y}px`;
            contextMenu.style.display = 'block';
            
            // 设置上下文菜单项可见性
            const isFile = target.dataset.type === 'file';
            document.querySelectorAll('.context-menu .file-only').forEach(item => {
                item.style.display = isFile ? 'flex' : 'none';
            });
            
            document.querySelectorAll('.context-menu .folder-only').forEach(item => {
                item.style.display = isFile ? 'none' : 'flex';
            });
            
            // 设置当前选中项
            contextMenu.dataset.path = target.dataset.path;
            contextMenu.dataset.type = target.dataset.type;
            contextMenu.dataset.name = target.querySelector('.item-name').textContent.trim();
        }
    });
    
    // 刷新菜单项
    contextRefresh.addEventListener('click', function() {
        window.location.reload();
        contextMenu.style.display = 'none';
    });
    
    // 下载文件菜单项
    contextDownload.addEventListener('click', function() {
        const filePath = contextMenu.dataset.path;
        
        if (filePath) {
            window.location.href = `/download/${filePath}`;
        }
        
        contextMenu.style.display = 'none';
    });
    
    // 上传到文件夹菜单项
    contextUpload.addEventListener('click', function() {
        const folderPath = contextMenu.dataset.path;
        
        if (folderPath) {
            const tempFileInput = document.createElement('input');
            tempFileInput.type = 'file';
            tempFileInput.multiple = true;
            
            tempFileInput.addEventListener('change', function() {
                if (tempFileInput.files.length > 0) {
                    uploadFiles(tempFileInput.files, folderPath);
                }
            });
            
            tempFileInput.click();
        }
        
        contextMenu.style.display = 'none';
    });
    
    // 下载整个文件夹菜单项
    contextDownloadAll.addEventListener('click', function() {
        const folderPath = contextMenu.dataset.path;
        
        if (folderPath) {
            const folderName = contextMenu.dataset.name.split(' ').pop();
            showModal(
                '下载文件夹',
                `准备下载文件夹 "${folderName}"，这可能需要一些时间来压缩文件。`,
                '开始下载',
                '取消',
                function() {
                    window.location.href = `/download/${folderPath}?type=folder`;
                }
            );
        }
        
        contextMenu.style.display = 'none';
    });
    
    // 点击其他地方关闭上下文菜单
    document.addEventListener('click', function() {
        contextMenu.style.display = 'none';
    });
    
    // 按ESC键关闭上下文菜单
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            contextMenu.style.display = 'none';
        }
    });
}

// 上传文件
async function uploadFiles(files, targetDir) {
    // 检查文件名冲突
    const fileNames = Array.from(files).map(file => file.name);
    
    try {
        const response = await fetch('/api/check_conflicts', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                target_dir: targetDir,
                filenames: fileNames
            })
        });
        
        const result = await response.json();
        
        if (result.has_conflicts) {
            showModal(
                '文件名冲突',
                `以下文件已存在，无法上传：<br>${result.conflicts.join('<br>')}`,
                '确定'
            );
            return;
        }
        
        // 显示上传进度容器
        const uploadProgressContainer = document.getElementById('upload-progress-container');
        const uploadProgressList = document.getElementById('upload-progress-list');
        uploadProgressContainer.style.display = 'block';
        
        // 为每个文件创建进度条
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const progressItemId = `upload-progress-${Date.now()}-${i}`;
            
            const progressItemHtml = `
                <div class="progress-item" id="${progressItemId}">
                    <div class="progress-info">
                        <span class="progress-filename">${file.name}</span>
                        <span class="progress-status">准备上传</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-bar-inner" style="width: 0%"></div>
                    </div>
                </div>
            `;
            
            uploadProgressList.insertAdjacentHTML('beforeend', progressItemHtml);
            
            // 上传文件
            await uploadFile(file, targetDir, progressItemId);
        }
        
        // 刷新文件列表
        window.location.reload();
        
    } catch (error) {
        console.error('上传错误:', error);
        showModal('上传错误', '上传文件时发生错误，请重试。', '确定');
    }
}

// 上传单个文件
async function uploadFile(file, targetDir, progressItemId) {
    try {
        // 开始上传
        const startResponse = await fetch('/api/start_upload', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                target_dir: targetDir,
                filename: file.name
            })
        });
        
        const startResult = await startResponse.json();
        const uploadId = startResult.upload_id;
        
        // 更新进度状态
        const progressItem = document.getElementById(progressItemId);
        const progressStatus = progressItem.querySelector('.progress-status');
        const progressBarInner = progressItem.querySelector('.progress-bar-inner');
        
        progressStatus.textContent = '上传中...';
        
        // 分块上传
        const chunkSize = 1024 * 1024; // 1MB
        const totalChunks = Math.ceil(file.size / chunkSize);
        
        for (let i = 0; i < totalChunks; i++) {
            const start = i * chunkSize;
            const end = Math.min(file.size, start + chunkSize);
            const chunk = file.slice(start, end);
            
            const formData = new FormData();
            formData.append('upload_id', uploadId);
            formData.append('file', chunk);
            formData.append('is_last_chunk', i === totalChunks - 1 ? 'true' : 'false');
            
            const response = await fetch(`/upload/${targetDir}`, {
                method: 'POST',
                body: formData
            });
            
            // 更新进度条
            const progress = Math.round(((i + 1) / totalChunks) * 100);
            progressBarInner.style.width = `${progress}%`;
            progressStatus.textContent = `上传中... ${progress}%`;
            
            // 如果是最后一块，检查结果
            if (i === totalChunks - 1) {
                const result = await response.json();
                
                if (result.success) {
                    progressStatus.textContent = '上传完成';
                } else {
                    progressStatus.textContent = '上传失败';
                    throw new Error(result.error || '上传失败');
                }
            }
        }
        
    } catch (error) {
        console.error('文件上传错误:', error);
        
        // 更新进度状态为失败
        const progressItem = document.getElementById(progressItemId);
        const progressStatus = progressItem.querySelector('.progress-status');
        progressStatus.textContent = '上传失败';
        
        throw error;
    }
}

// 队列下载文件
async function queueDownloads(filePaths) {
    try {
        // 如果没有会话ID，创建一个新的
        if (!currentSessionId) {
            currentSessionId = Date.now().toString();
        }
        
        const response = await fetch('/api/queue_download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                paths: filePaths,
                session_id: currentSessionId
            })
        });
        
        const result = await response.json();
        
        if (result.added_files > 0) {
            // 显示下载进度容器
            const downloadProgressContainer = document.getElementById('download-progress-container');
            const downloadProgressList = document.getElementById('download-progress-list');
            downloadProgressContainer.style.display = 'block';
            
            // 为每个文件创建下载项
            filePaths.forEach(path => {
                const fileName = path.split('/').pop();
                const downloadItemId = `download-item-${Date.now()}-${fileName.replace(/[^a-zA-Z0-9]/g, '-')}`;
                
                const downloadItemHtml = `
                    <div class="progress-item" id="${downloadItemId}">
                        <div class="progress-info">
                            <span class="progress-filename">${fileName}</span>
                            <span class="progress-status">队列中</span>
                        </div>
                        <div class="download-actions">
                            <a href="/download/${path}" class="btn primary" download>立即下载</a>
                        </div>
                    </div>
                `;
                
                downloadProgressList.insertAdjacentHTML('beforeend', downloadItemHtml);
            });
            
            // 清除选中状态
            selectedFiles.clear();
            document.querySelectorAll('.file-checkbox').forEach(checkbox => {
                checkbox.checked = false;
            });
            document.getElementById('select-all').checked = false;
            updateDownloadButtonState();
            
        } else {
            showModal('下载错误', '添加文件到下载队列失败，请重试。', '确定');
        }
        
    } catch (error) {
        console.error('下载队列错误:', error);
        showModal('下载错误', '添加文件到下载队列失败，请重试。', '确定');
    }
}

// 显示模态对话框
function showModal(title, message, confirmText = '确定', cancelText = '取消', onConfirm = null) {
    const modal = document.getElementById('modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');
    const modalConfirm = document.getElementById('modal-confirm');
    const modalCancel = document.getElementById('modal-cancel');
    
    modalTitle.textContent = title;
    modalBody.innerHTML = message;
    modalConfirm.textContent = confirmText;
    modalCancel.textContent = cancelText;
    
    if (onConfirm) {
        modalConfirm.onclick = function() {
            onConfirm();
            closeModal();
        };
    } else {
        modalConfirm.onclick = closeModal;
    }
    
    modal.style.display = 'block';
}

// 关闭模态对话框
function closeModal() {
    const modal = document.getElementById('modal');
    modal.style.display = 'none';
}
