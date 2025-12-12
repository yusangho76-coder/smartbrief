# 🚀 빠른 시작 가이드 - 5분 안에 배포하기

이 가이드는 처음 배포하는 분들을 위한 **단계별 실전 가이드**입니다.


**이 가이드는 Cloud Run에 배포하는 방법입니다.**
- ✅ **gcloud CLI만 필요** - Google Cloud SDK만 설치하면 됩니다

## 📋 준비물 체크리스트

배포를 시작하기 전에 다음을 확인하세요:

- [ ] Google 계정 (Gmail 계정으로 충분)
- [ ] Gemini API 키 (아래에서 발급 방법 확인)
- [ ] 터미널 접근 가능 (macOS, Linux, Windows)
- [ ] **Python 설치 불필요!** ✅ (배포만 하려면 필요 없음)

---

## 1단계: Google Cloud SDK 설치 (5분)

### macOS 사용자

터미널을 열고 다음 명령어 실행:

```bash
# Homebrew가 설치되어 있다면
brew install google-cloud-sdk

# Homebrew가 없다면
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

**확인:**
```bash
gcloud --version
```
버전 정보가 나오면 성공!

### Windows 사용자

1. 브라우저에서 https://docs.cloud.google.com/sdk/docs/install-sdk?hl=ko#windows 접속
2. "Windows" 탭 클릭
3. 설치 프로그램 다운로드 및 실행
4. PowerShell 또는 Command Prompt 열기

**확인:**
```powershell
gcloud --version
```
---

## 2단계: Gemini API 키 발급 (2분)

1. 브라우저에서 https://makersuite.google.com/app/apikey 접속
2. Google 계정으로 로그인
3. "Create API Key" 버튼 클릭
4. API 키 복사 (예: `AIzaSy...`)

**⚠️ 중요:** 이 API 키를 안전하게 보관하세요. 나중에 사용합니다!

---

## 3단계: 프로젝트 디렉토리로 이동

터미널에서 프로젝트 폴더로 이동:

```bash
cd "/Users/sunghyunkim/Documents/Documents - Sunghyun/SmartNOTAM3_GCR_James (9)"
```

또는 실제 프로젝트 경로로 이동하세요.

---

## 4단계: 배포 실행 (가장 쉬운 방법)

### 방법 A: 대화형 모드 (추천! ⭐)

터미널에서 다음 명령어 실행:

```bash
./deploy/deploy_simple.sh --interactive
```

**스크립트가 물어보는 것들:**

1. **프로젝트 ID**: 
   - Enter 키만 누르면 자동 생성됨 (추천!)
   - 또는 원하는 ID 입력 (예: `smartnotam-123`)

2. **리전**: 
   - Enter 키만 누르면 서울(asia-northeast3) 사용 (추천!)

3. **Gemini API 키**: 
   - 2단계에서 복사한 API 키 붙여넣기 (필수!)

4. **이메일**: 
   - Enter 키만 누르면 현재 로그인한 계정 사용 (추천!)

**그 다음:**
- 브라우저가 열리면 Google 계정으로 로그인
- 스크립트가 자동으로 나머지 작업 수행
- 5-10분 정도 소요

**완료되면:**
```
✅ 배포 완료!
배포 URL: https://smartnotam-xxxxx-xx.a.run.app
```
이 URL을 브라우저에서 열어 확인하세요!

---

### 방법 B: 설정 파일 사용

#### 4-1. 설정 파일 생성

```bash
cp deploy/config.example.sh deploy/config.sh
```

#### 4-2. 설정 파일 편집

터미널에서:

```bash
# macOS/Linux
nano deploy/config.sh

# 또는 원하는 에디터 사용
# code deploy/config.sh  (VS Code)
# vim deploy/config.sh
```

**Windows 사용자:**
- 메모장이나 VS Code로 `deploy/config.sh` 파일 열기

#### 4-3. 필수 값만 입력

파일을 열면 다음과 같이 보입니다:

```bash
PROJECT_ID=""              # 비워두면 자동 생성 (추천!)
REGION="asia-northeast3"   # 그대로 두기 (서울)
REPO="smartnotam-repo"     # 그대로 두기
SERVICE="smartnotam"       # 그대로 두기
GEMINI_API_KEY=""          # 여기에 API 키 입력! (필수!)
GRANTEE_EMAIL=""           # 비워두면 현재 계정 사용 (추천!)
```

**수정할 것:**
- `GEMINI_API_KEY="AIzaSy..."` ← 여기에 2단계에서 복사한 API 키 붙여넣기

**저장:**
- nano: `Ctrl + X`, `Y`, `Enter`
- 메모장/VS Code: `Ctrl + S` (Windows) 또는 `Cmd + S` (Mac)

#### 4-4. 배포 실행

```bash
./deploy/deploy_simple.sh
```

**그 다음:**
- 브라우저가 열리면 Google 계정으로 로그인
- 스크립트가 자동으로 나머지 작업 수행
- 5-10분 정도 소요

---

## 5단계: 배포 확인

배포가 완료되면 다음과 같은 메시지가 나타납니다:

```
✅ 배포 완료!
배포 URL: https://smartnotam-xxxxx-xx.a.run.app
```

**확인 방법:**
1. 브라우저에서 위 URL 열기
2. 웹사이트가 정상적으로 보이면 성공! ✅

---

## 🎉 완료!

축하합니다! 배포가 완료되었습니다.

이제 다음을 할 수 있습니다:

### 애플리케이션 사용
- 배포된 URL로 접속하여 NOTAM 파일 업로드 및 처리

### 재배포 (코드 수정 후)
```bash
./deploy/deploy_simple.sh
```
또는
```bash
./deploy/deploy_simple.sh --interactive
```

### 배포 정보 확인
```bash
# 배포 URL 확인
gcloud run services describe smartnotam \
  --region asia-northeast3 \
  --format="value(status.url)"

# 로그 확인
gcloud run services logs read smartnotam \
  --region asia-northeast3 \
  --limit 50
```

---

## ❌ 문제가 발생했다면?

### "gcloud: command not found"
→ 1단계를 다시 확인하세요. SDK가 제대로 설치되지 않았습니다.

### "Permission denied"
```bash
chmod +x deploy/deploy_simple.sh
```

### "설정 파일이 없습니다"
→ 방법 B를 사용하는 경우, 4-1단계를 다시 확인하세요.

### "로그인 실패"
→ 브라우저에서 올바른 Google 계정으로 로그인했는지 확인하세요.

### "배포는 성공했지만 404 오류"
→ [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) 참고

**더 많은 문제 해결:** [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

---

## 📚 다음 단계

- [상세 배포 가이드](./DEPLOYMENT_GUIDE_KR.md) - 더 자세한 설명
- [문제 해결](./TROUBLESHOOTING.md) - 오류 해결 방법
- [비용 정보](./COST_COMPARISON.md) - 비용 상세 정보

---

## 💡 팁

1. **Python 설치 불필요!**
   - 배포만 하려면 Python이 필요 없습니다
   - gcloud CLI만 설치하면 됩니다
   - Cloud Build가 자동으로 빌드합니다

2. **처음 배포는 방법 A (대화형 모드) 추천**
   - 설정 파일을 만들 필요 없음
   - 스크립트가 모든 것을 안내

3. **프로젝트 ID는 자동 생성 추천**
   - 중복 걱정 없음
   - 고유한 ID 자동 생성

4. **배포는 5-10분 소요**
   - Docker 이미지 빌드 시간 포함
   - 네트워크 속도에 따라 다를 수 있음
   - **Python 설치나 코드 수정 불필요!** ✅

5. **무료 티어 충분**
   - 일반적인 사용은 완전 무료
   - 월 10회 사용 시 $0

---

## ❓ 자주 묻는 질문

### Q: Python을 설치해야 하나요?
**A: 아니요! 배포만 하려면 Python이 필요 없습니다.**
- Cloud Run 배포는 gcloud CLI만 필요합니다
- Cloud Build가 자동으로 Docker 이미지를 빌드합니다
- Python은 로컬에서 개발할 때만 필요합니다

### Q: 코드를 수정해야 하나요?
**A: 아니요! 이미 완성된 앱을 배포합니다.**
- 코드 수정 불필요
- 설정만 하면 바로 배포 가능

### Q: 로컬에서 테스트하고 싶어요
**A: 그 경우에만 Python이 필요합니다.**
- 로컬 개발: Python 3.11+ 필요
- 배포만: Python 불필요 ✅

---

**질문이 있으면 이슈를 등록하세요!**

**행운을 빕니다! 🚀**
