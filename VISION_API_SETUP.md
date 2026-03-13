# Google Cloud Vision API 설정 가이드

## 개요

Google Cloud Vision API는 색상 추출에 가장 정확한 방법입니다. IMAGE_PROPERTIES 기능으로 정확한 RGB 값을 추출할 수 있습니다.

## 설정 단계

### 1. Google Cloud 프로젝트 생성

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택

### 2. Vision API 활성화

1. Cloud Console에서 "API 및 서비스" > "라이브러리" 이동
2. "Cloud Vision API" 검색
3. "사용 설정" 클릭

### 3. 서비스 계정 키 생성

1. "API 및 서비스" > "사용자 인증 정보" 이동
2. "사용자 인증 정보 만들기" > "서비스 계정" 선택
3. 서비스 계정 이름 입력 (예: `vision-api-service`)
4. 역할: "Cloud Vision API 사용자" 선택
5. "키 만들기" > "JSON" 선택
6. JSON 키 파일 다운로드

### 4. 환경 변수 설정

#### macOS/Linux:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/key.json"
```

#### Windows:
```cmd
set GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\your\key.json
```

#### .env 파일 사용 (권장):
`.env` 파일에 추가:
```
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/key.json
```

### 5. 라이브러리 설치

```bash
pip3 install google-cloud-vision
```

## 테스트

```bash
python3 test_vision_api.py
```

## 비용

Google Cloud Vision API는 무료 할당량이 있습니다:
- 월 1,000회 요청까지 무료
- 그 이후: $1.50 per 1,000 requests

## 문제 해결

### 인증 오류
- `GOOGLE_APPLICATION_CREDENTIALS` 환경 변수가 올바르게 설정되었는지 확인
- JSON 키 파일 경로가 정확한지 확인
- 서비스 계정에 Vision API 권한이 있는지 확인

### API 활성화 오류
- Cloud Console에서 Vision API가 활성화되었는지 확인
- 프로젝트가 올바르게 선택되었는지 확인

