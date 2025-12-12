// Smart NOTAM 메인 JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // 파일 업로드 폼 처리
    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('file');
    const loadingModal = new bootstrap.Modal(document.getElementById('loadingModal'));
    
    // 드래그 앤 드롭 기능
    setupDragAndDrop();
    
    // 파일 선택 시 유효성 검사
    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                validateFile(file);
            }
        });
    }
    
    // 폼 제출 시 로딩 모달 표시
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            const file = fileInput.files[0];
            if (!file) {
                e.preventDefault();
                showAlert('파일을 선택해주세요.', 'warning');
                return;
            }
            
            if (!validateFile(file)) {
                e.preventDefault();
                return;
            }
            
            // 로딩 모달 표시
            loadingModal.show();
        });
    }
});

function setupDragAndDrop() {
    const uploadArea = document.querySelector('.card-body');
    if (!uploadArea) return;
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });
    
    ['dragenter', 'dragover'].forEach(eventName => {
        uploadArea.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, unhighlight, false);
    });
    
    uploadArea.addEventListener('drop', handleDrop, false);
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight(e) {
        uploadArea.classList.add('dragover');
    }
    
    function unhighlight(e) {
        uploadArea.classList.remove('dragover');
    }
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0) {
            const fileInput = document.getElementById('file');
            fileInput.files = files;
            validateFile(files[0]);
        }
    }
}

function validateFile(file) {
    const allowedTypes = ['application/pdf'];
    const maxSize = 16 * 1024 * 1024; // 16MB
    
    if (!allowedTypes.includes(file.type)) {
        showAlert('PDF 파일만 업로드 가능합니다.', 'error');
        return false;
    }
    
    if (file.size > maxSize) {
        showAlert('파일 크기는 16MB를 초과할 수 없습니다.', 'error');
        return false;
    }
    
    showAlert(`파일 "${file.name}"이 선택되었습니다.`, 'success');
    return true;
}

function showAlert(message, type = 'info') {
    // 기존 알림 제거
    const existingAlert = document.querySelector('.dynamic-alert');
    if (existingAlert) {
        existingAlert.remove();
    }
    
    const alertClass = {
        'success': 'alert-success',
        'error': 'alert-danger',
        'warning': 'alert-warning',
        'info': 'alert-info'
    }[type] || 'alert-info';
    
    const alertHTML = `
        <div class="alert ${alertClass} alert-dismissible fade show dynamic-alert" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    const container = document.querySelector('.container');
    container.insertAdjacentHTML('afterbegin', alertHTML);
    
    // 3초 후 자동 제거
    setTimeout(() => {
        const alert = document.querySelector('.dynamic-alert');
        if (alert) {
            alert.remove();
        }
    }, 3000);
}

function showLoading(show = true) {
    const loadingOverlay = document.getElementById('loadingOverlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = show ? 'flex' : 'none';
    }
}

// 페이지 언로드 시 로딩 상태 표시
window.addEventListener('beforeunload', function() {
    showLoading(true);
});

// 툴팁 초기화
document.addEventListener('DOMContentLoaded', function() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// 유틸리티 함수들
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDateTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('ko-KR') + ' ' + date.toLocaleTimeString('ko-KR');
}

// 에러 처리
window.addEventListener('error', function(e) {
    console.error('JavaScript Error:', e.error);
    showAlert('예상치 못한 오류가 발생했습니다.', 'error');
});

// AJAX 요청 헬퍼
function makeRequest(url, options = {}) {
    const defaultOptions = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        },
    };
    
    const finalOptions = { ...defaultOptions, ...options };
    
    return fetch(url, finalOptions)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .catch(error => {
            console.error('Request failed:', error);
            showAlert('서버 요청 중 오류가 발생했습니다.', 'error');
            throw error;
        });
}