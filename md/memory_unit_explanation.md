# 메모리 단위: GB vs GiB 차이 설명

## 기본 개념

### 십진법 기반 단위 (SI 단위)
- **GB (Gigabyte)**: 10^9 = 1,000,000,000 bytes (10억 바이트)
- **MB (Megabyte)**: 10^6 = 1,000,000 bytes (100만 바이트)
- **KB (Kilobyte)**: 10^3 = 1,000 bytes (1천 바이트)

### 이진법 기반 단위 (IEC 단위)
- **GiB (Gibibyte)**: 2^30 = 1,073,741,824 bytes (약 10.7억 바이트)
- **MiB (Mebibyte)**: 2^20 = 1,048,576 bytes (약 105만 바이트)
- **KiB (Kibibyte)**: 2^10 = 1,024 bytes

---

## 정확한 변환

| 이진법 (GiB) | 십진법 (GB) | 차이 |
|-------------|------------|------|
| 1 GiB | 1.073741824 GB | 약 7.37% 더 큼 |
| 2 GiB | 2.147483648 GB | 약 7.37% 더 큼 |
| 4 GiB | 4.294967296 GB | 약 7.37% 더 큼 |
| 8 GiB | 8.589934592 GB | 약 7.37% 더 큼 |

**1 GiB = 1024 MiB = 1024 × 1024 KiB = 1024 × 1024 × 1024 bytes**

---

## 왜 두 가지 단위가 존재하나요?

### 역사적 이유
1. **과거**: 컴퓨터 메모리는 이진법 기반 (2의 제곱)으로 동작
   - 메모리 주소: 2진수로 구성
   - 실제로는 1024 = 2^10 단위가 자연스러움

2. **명명 혼란**: 
   - 하드웨어 제조사는 십진법(GB) 사용 (용량을 크게 보이게)
   - 운영체제/소프트웨어는 이진법(GiB) 사용 (실제 메모리 계산)
   - 같은 "GB"라도 의미가 다름

3. **표준화 시도**:
   - 1998년 IEC가 명확하게 구분하기 위해 GiB, MiB, KiB 도입
   - 하지만 여전히 혼용됨

---

## 실제 사용 예시

### 하드웨어 (십진법 사용)
- 하드디스크: "1TB" = 1,000,000,000,000 bytes
- USB 메모리: "64GB" = 64,000,000,000 bytes

### 운영체제 (이진법 사용)
- Windows: "2GB RAM" 표시지만 실제로는 2^31 bytes (2 GiB)
- Linux: `/proc/meminfo`에서 KiB, MiB, GiB 단위 명시
- macOS: GiB 단위 사용

### 클라우드 서비스
- **Google Cloud Run**: **GiB 단위 사용** (`--memory 2Gi`)
- **AWS Lambda**: GB 단위 사용 (실제로는 이진법 계산)
- **Azure Functions**: GB 단위 사용

---

## Google Cloud Run에서의 사용

### 현재 설정
```bash
--memory 2Gi  # = 2 Gibibyte = 2,147,483,648 bytes
```

### 다른 옵션들
```bash
--memory 128Mi  # 128 Mebibyte
--memory 512Mi  # 512 Mebibyte
--memory 1Gi    # 1 Gibibyte
--memory 2Gi    # 2 Gibibyte (현재 설정)
--memory 4Gi    # 4 Gibibyte
--memory 8Gi    # 8 Gibibyte
```

---

## 왜 Google Cloud Run은 GiB를 사용하나요?

1. **정확성**: 컨테이너 메모리 관리는 이진법 기반
2. **명확성**: GB와 GiB를 구분하여 혼동 방지
3. **표준 준수**: IEC 표준 단위 사용

---

## 실무에서 기억할 점

### 간단 계산식
- **1 GiB ≈ 1.07 GB** (약 7% 차이)
- **2 GiB ≈ 2.15 GB**
- **4 GiB ≈ 4.29 GB**

### 명확하게 이해하기
- **Google Cloud Run의 `2Gi`**: 실제로는 2,147,483,648 bytes
- **만약 `2G`라고 표기했다면**: 2,000,000,000 bytes (실제로는 약 147MB 적음)

### 결론
**Cloud Run 설정에서 `2Gi`는 실제로 약 2.15GB의 메모리를 의미합니다.**
