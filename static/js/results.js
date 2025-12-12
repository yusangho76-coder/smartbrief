// Smart NOTAM 결과 페이지 JavaScript

let currentNotams = [];
let currentMapData = [];

document.addEventListener('DOMContentLoaded', function() {
    // 초기 데이터 설정
    if (typeof notams !== 'undefined') {
        currentNotams = notams;
    }
    if (typeof mapData !== 'undefined') {
        currentMapData = mapData;
    }
    
    // 이벤트 리스너 설정
    setupEventListeners();
    
    // 툴팁 초기화
    initializeTooltips();
});

function setupEventListeners() {
    // 필터 적용 버튼
    const applyFilterBtn = document.querySelector('button[onclick="applyFilters()"]');
    if (applyFilterBtn) {
        applyFilterBtn.addEventListener('click', applyFilters);
    }
    
    // 필터 리셋 버튼
    const resetFilterBtn = document.querySelector('button[onclick="resetFilters()"]');
    if (resetFilterBtn) {
        resetFilterBtn.addEventListener('click', resetFilters);
    }
    
    // 브리핑 생성 버튼
    const briefingBtn = document.querySelector('button[onclick="generateBriefing()"]');
    if (briefingBtn) {
        briefingBtn.addEventListener('click', generateBriefing);
    }
}

function applyFilters() {
    showLoading(true);
    
    const filters = {
        start_date: document.getElementById('startDate')?.value,
        end_date: document.getElementById('endDate')?.value,
        airports: Array.from(document.getElementById('airportFilter')?.selectedOptions || []).map(option => option.value),
        types: Array.from(document.querySelectorAll('input[type="checkbox"]:checked')).map(cb => cb.value)
    };
    
    // 필터링 요청
    fetch('/filter', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            notams: currentNotams,
            filters: filters
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateNotamList(data.notams);
            updateMap(data.map_data);
            showAlert(`${data.notams.length}개의 NOTAM이 필터링되었습니다.`, 'success');
        } else {
            showAlert('필터링 중 오류가 발생했습니다: ' + data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Filter error:', error);
        showAlert('필터링 요청 중 오류가 발생했습니다.', 'error');
    })
    .finally(() => {
        showLoading(false);
    });
}

function resetFilters() {
    // 모든 필터 입력 초기화
    document.getElementById('startDate').value = '';
    document.getElementById('endDate').value = '';
    document.getElementById('airportFilter').selectedIndex = -1;
    document.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
    
    // 원본 데이터로 복원
    updateNotamList(currentNotams);
    updateMap(currentMapData);
    showAlert('필터가 초기화되었습니다.', 'info');
}

function updateNotamList(notams) {
    const notamList = document.getElementById('notamList');
    if (!notamList) return;
    
    if (notams.length === 0) {
        notamList.innerHTML = `
            <div class="text-center py-4">
                <i class="fas fa-search fa-3x text-muted mb-3"></i>
                <h5 class="text-muted">필터 조건에 맞는 NOTAM이 없습니다.</h5>
            </div>
        `;
        return;
    }
    
    let html = '';
    notams.forEach(notam => {
        html += createNotamCard(notam);
    });
    
    notamList.innerHTML = html;
    
    // 애니메이션 효과 추가
    notamList.classList.add('fade-in');
}

function createNotamCard(notam) {
    const airports = notam.airport_codes ? notam.airport_codes.map(code => 
        `<span class="badge bg-secondary ms-1">${code}</span>`
    ).join('') : '';
    const notamNumberDisplay = notam.notam_number_display || notam.id || '';
    
    const coordinates = notam.coordinates ? 
        `<p class="text-muted small mb-1">좌표</p>
         <p>${notam.coordinates.latitude.toFixed(6)}, ${notam.coordinates.longitude.toFixed(6)}</p>` : '';
    
    const translation = notam.translated_description ? 
        `<div class="mt-3">
            <p class="text-muted small mb-1">번역</p>
            <div class="border p-2 bg-info bg-opacity-10">
                ${notam.translated_description}
            </div>
         </div>` : '';
    
    const summary = notam.summary ? 
        `<div class="mt-3">
            <p class="text-muted small mb-1">요약</p>
            <div class="border p-2 bg-warning bg-opacity-10">
                ${notam.summary}
            </div>
         </div>` : '';
    
    return `
        <div class="card mb-3 notam-item" data-notam-id="${notam.id}">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h6 class="mb-0">
                    <span class="badge bg-primary">${notamNumberDisplay}</span>
                    ${airports}
                </h6>
                <div>
                    <button class="btn btn-sm btn-outline-primary" onclick="translateNotam('${notam.id}')" 
                            data-bs-toggle="tooltip" title="번역">
                        <i class="fas fa-language"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-success" onclick="summarizeNotam('${notam.id}')"
                            data-bs-toggle="tooltip" title="요약">
                        <i class="fas fa-compress-alt"></i>
                    </button>
                </div>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <p class="text-muted small mb-1">유효기간</p>
                        <p>${notam.effective_time} ~ ${notam.expiry_time}</p>
                    </div>
                    <div class="col-md-6">
                        ${coordinates}
                    </div>
                </div>
                
                <div class="mt-3">
                    <p class="text-muted small mb-1">원문</p>
                    <div class="border p-2 bg-light small">
                        ${notam.description}
                    </div>
                </div>
                
                ${translation}
                ${summary}
            </div>
        </div>
    `;
}

function translateNotam(notamId) {
    const notamCard = document.querySelector(`[data-notam-id="${notamId}"]`);
    if (!notamCard) return;
    
    const descriptionEl = notamCard.querySelector('.bg-light');
    const originalText = descriptionEl.textContent.trim();
    
    showLoading(true);
    
    fetch('/translate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text: originalText })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 번역 결과 표시
            let translationDiv = notamCard.querySelector('.bg-info');
            if (!translationDiv) {
                const cardBody = notamCard.querySelector('.card-body');
                cardBody.insertAdjacentHTML('beforeend', `
                    <div class="mt-3">
                        <p class="text-muted small mb-1">번역</p>
                        <div class="border p-2 bg-info bg-opacity-10">
                            ${data.translated_text}
                        </div>
                    </div>
                `);
            } else {
                translationDiv.textContent = data.translated_text;
            }
            showAlert('번역이 완료되었습니다.', 'success');
        } else {
            showAlert('번역 중 오류가 발생했습니다: ' + data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Translation error:', error);
        showAlert('번역 요청 중 오류가 발생했습니다.', 'error');
    })
    .finally(() => {
        showLoading(false);
    });
}

function summarizeNotam(notamId) {
    const notam = currentNotams.find(n => n.id === notamId);
    if (!notam) return;
    
    showLoading(true);
    
    fetch('/summary', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ notam: notam })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 요약 결과 표시
            const notamCard = document.querySelector(`[data-notam-id="${notamId}"]`);
            let summaryDiv = notamCard.querySelector('.bg-warning');
            if (!summaryDiv) {
                const cardBody = notamCard.querySelector('.card-body');
                cardBody.insertAdjacentHTML('beforeend', `
                    <div class="mt-3">
                        <p class="text-muted small mb-1">요약</p>
                        <div class="border p-2 bg-warning bg-opacity-10">
                            ${data.summary}
                        </div>
                    </div>
                `);
            } else {
                summaryDiv.textContent = data.summary;
            }
            showAlert('요약이 완료되었습니다.', 'success');
        } else {
            showAlert('요약 중 오류가 발생했습니다: ' + data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Summary error:', error);
        showAlert('요약 요청 중 오류가 발생했습니다.', 'error');
    })
    .finally(() => {
        showLoading(false);
    });
}

function generateBriefing() {
    showLoading(true);
    
    fetch('/briefing', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
            notams: currentNotams,
            flight_route: [] // 필요시 입력받도록 수정
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('briefingContent').innerHTML = `
                <pre class="code-block">${data.briefing}</pre>
            `;
            const briefingModal = new bootstrap.Modal(document.getElementById('briefingModal'));
            briefingModal.show();
        } else {
            showAlert('브리핑 생성 중 오류가 발생했습니다: ' + data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Briefing error:', error);
        showAlert('브리핑 생성 요청 중 오류가 발생했습니다.', 'error');
    })
    .finally(() => {
        showLoading(false);
    });
}

function downloadBriefing() {
    const content = document.getElementById('briefingContent').textContent;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `NOTAM_Briefing_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    showAlert('브리핑이 다운로드되었습니다.', 'success');
}

function updateMap(mapData) {
    if (typeof map === 'undefined') return;
    
    // 기존 마커 제거
    if (typeof markers !== 'undefined') {
        markers.forEach(marker => marker.setMap(null));
        markers = [];
    }
    
    // 새 마커 추가
    mapData.forEach(function(notam) {
        const marker = new google.maps.Marker({
            position: { lat: notam.latitude, lng: notam.longitude },
            map: map,
            title: notam.title
        });
        
        const infoWindow = new google.maps.InfoWindow({
            content: `
                <div>
                    <h6>${notam.title}</h6>
                    <p>${notam.description}</p>
                </div>
            `
        });
        
        marker.addListener("click", () => {
            infoWindow.open(map, marker);
        });
        
        markers.push(marker);
    });
    
    // 마커들이 모두 보이도록 지도 범위 조정
    if (markers.length > 0) {
        const bounds = new google.maps.LatLngBounds();
        markers.forEach(marker => bounds.extend(marker.getPosition()));
        map.fitBounds(bounds);
    }
}

function showLoading(show = true) {
    const loadingOverlay = document.getElementById('loadingOverlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = show ? 'flex' : 'none';
    }
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

function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}