# Cloud Run Internal Server Error (500) 디버깅

**SHOW_SERVER_ERROR_DETAIL=1 을 넣었는데도 화면에 에러가 안 보이면** → 에러가 **앱 시작(import) 단계**에서 나는 경우입니다. 이때는 반드시 **아래 1번(로그)** 로 확인해야 합니다.

---

## 1. Cloud Run 로그로 원인 확인 (권장)

1. [Google Cloud Console](https://console.cloud.google.com/) 접속 후 **프로젝트 선택**
2. 왼쪽 메뉴(≡) → **Cloud Run** → 서비스 **smartnotam3** 클릭
3. 상단 **로그** 탭 클릭 (또는 **Observability** → **로그**)
4. **심각도**에서 **오류** 선택, 또는 검색창에 `Traceback` 또는 `Error` 입력
5. 500이 난 시각 근처의 로그를 열어 **Python traceback** (`Traceback (most recent call last):` … `Error: ...`) 확인

**로그 탐색기 직접 열기:**  
[로그 탐색기](https://console.cloud.google.com/logs/query) → 리소스 타입 **Cloud Run 리비전** 선택 → 서비스 `smartnotam3` 선택 → 쿼리에 `severity>=ERROR` 입력 후 실행

콘솔 대신 gcloud 사용:

```bash
gcloud run services logs read smartnotam3 --region=asia-northeast3 --limit=100
```

## 2. 앱에서 500 상세 내용 보기 (임시 디버그)

배포 시 환경 변수로 500 발생 시 **응답 본문에 에러/트레이스백**을 노출할 수 있습니다.

- **Cloud Run** 서비스 수정 → **변수 및 시크릿** → 변수 추가:
  - 이름: `SHOW_SERVER_ERROR_DETAIL`
  - 값: `1`
- 재배포 후 500이 나는 URL 다시 접속 → 브라우저에 에러 메시지와 traceback이 출력됨
- **원인 확인 후 반드시 해당 변수 제거** (프로덕션에서는 보안상 제거)

## 3. 자주 나오는 원인

| 현상 | 가능 원인 |
|------|-----------|
| `FileNotFoundError: ... fir.geojson` | `NavData`가 이미지에 없음 → `.dockerignore`에 `NavData` 제외 여부 확인 |
| `KeyError`, `API key not valid` | `GEMINI_API_KEY` / `GOOGLE_MAPS_API_KEY` 미설정 또는 오타 (Cloud Run 변수/시크릿 확인) |
| `ModuleNotFoundError`, `ImportError` | `requirements.txt` 누락 패키지 또는 경로 문제 |
| `PermissionError`, `Read-only` | 컨테이너 내 쓰기 시도 경로 → `/tmp` 등 쓸 수 있는 경로 사용 |

로그에 나온 **정확한 에러 메시지/트레이스백**을 기준으로 위 항목과 대조해 보시면 됩니다.
