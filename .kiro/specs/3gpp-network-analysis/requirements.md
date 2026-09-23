# Requirements Document

**버전**: 3.0  
**작성일**: 2025  
**언어 정책**: 본 문서는 한국어로 작성하되, 3GPP, TSG, WG, TDoc, Work Item, Release, Edge, Parquet 등 고유 기술 용어는 영어 원문을 그대로 사용한다.

---

## Introduction

본 시스템은 3GPP 표준화 기구의 기고서(TDoc) 메타데이터를 수집·전처리하여 기업 간 협력 구조를 네트워크로 분석하고, 그 결과를 인터랙티브 대시보드로 제공하는 지속적 분석 파이프라인이다.

기존 석사 논문 연구(2024년)에서 구축한 Jupyter Notebook 기반 파이프라인의 코드 자산을 계승하되, **자동화·확장성·재현성**을 갖춘 운영 가능한 시스템으로 재구성한다. 기존 `raw/` 폴더의 원본 노트북은 **참조 전용으로 보존**하며 어떠한 경우에도 수정하지 않는다.

### 핵심 설계 원칙

1. **절차 중심**: 파이프라인의 각 단계가 누락 없이 순차적으로 정의된다.
2. **데이터 기반 규칙 도출**: 각 단계에서 하드코딩된 규칙이 아닌, 데이터 분석을 통해 규칙을 도출하고 검증한다.
3. **설정 외부화**: 도출된 규칙은 `config/` 디렉토리의 YAML 파일에서 관리하여 코드 수정 없이 변경 가능하다.
4. **기존 규칙 참고**: 기존 분석에서 사용했던 규칙은 참고 예시로 포함하되, 구현 시 데이터 검증을 통해 확정한다.

### 파이프라인 구조 (총 9단계, Source 처리 단계 통합 포함)

기존 노트북의 Source 처리는 Explode → Filter → Matching 3단계로 이루어져 있었으나, 본 시스템은 이를 **멤버십 기반 추출(Stage 3)** 1단계로 통합하였다. (파이프라인 전체는 아래 표와 같이 Collector~Dashboard까지 총 9단계이며, "단순화"는 Source 처리 세부 단계의 축소만을 의미한다.)

| 단계 | 설명 |
|------|------|
| Stage 1: Collector | FTP에서 TDoc List xlsx 파일 수집 |
| Stage 1.5: Parser | xlsx 파일을 표준화된 DataFrame으로 파싱 |
| Stage 2: Title Filter | 분석 대상이 아닌 기고서 유형 제외 |
| Stage 3: Membership-based Extraction | **Source에서 멤버십 기업명 직접 추출 (통합)** |
| Stage 4: WI Explode | 복수 Work Item을 개별 행으로 분리 |
| Stage 5: Temporal Enrichment | 시간 정보(Year, Quarter) 추가 및 필터링 |
| Stage 6: Network Builder | 기업 간/WI 간 협력 네트워크 Edge 생성 |
| Stage 7: Network Analyzer | 네트워크 통계, 중심성, 커뮤니티 분석 |
| Stage 8: Dashboard | 인터랙티브 시각화 |

---

## Glossary

- **3GPP**: 3rd Generation Partnership Project. 이동통신 국제 표준화 기구.
- **TSG**: Technical Specification Group. 3GPP 내 최상위 기술 조직 단위. RAN, SA, CT 세 그룹으로 구성.
- **WG**: Working Group. TSG 산하의 세부 작업 그룹(예: RAN1, SA2, CT4 등).
- **TDoc**: Technical Document. 3GPP 회의에 제출되는 기고서. TSG 회차별 FTP 서버에 메타데이터 목록(xlsx)이 공개된다.
- **Work Item (WI)**: 3GPP에서 특정 기술 기능을 정의하고 표준화하는 작업 단위. 코드로 식별된다.
- **Release**: 3GPP가 주기적으로 출시하는 표준 버전. Rel.15(5G 기반), Rel.16, Rel.17, Rel.18, Rel.19(5G-Advanced) 등.
- **Source**: TDoc의 제출 주체. 단일 기업 또는 복수 기업이 공동 제출할 수 있다.
- **Edge**: 네트워크에서 두 노드 간 관계를 나타내는 연결선. Edge Weight는 공동 기고 횟수를 의미한다.
- **Louvain**: 커뮤니티 탐지를 위한 그래프 클러스터링 알고리즘.
- **ETSI 멤버십**: 유럽전기통신표준화기구(ETSI)가 관리하는 3GPP 회원사 공식 목록. 기업 이름 정규화의 기준 데이터로 사용된다.
- **Pipeline**: 데이터 수집 → 전처리 → 네트워크 구성 → 분석 → 시각화의 순차적 처리 흐름.
- **멤버십 기반 추출**: Source 문자열 전체에서 ETSI 멤버십 기업명을 직접 탐색하여 추출하는 방식. 기존의 분리(Explode) → 필터(Filter) → 매칭(Matching) 3단계를 1단계로 통합한다.

---

## 데이터 기반 규칙 도출 프로세스

각 전처리 단계에서 아래 프로세스를 따른다:

1. **데이터 샘플링 및 패턴 분석**: 해당 단계의 대상 데이터를 샘플링하여 패턴을 식별한다.
2. **규칙 후보 도출**: 기존 분석 규칙을 참고하여 규칙 후보를 정의한다.
3. **영향도 분석**: 규칙 적용 전후 제거/변환되는 레코드 수와 비율을 측정한다.
4. **규칙 확정**: 영향도 분석 결과를 검토하여 규칙을 확정하고 `config/` 파일에 기록한다.
5. **예외 케이스 처리**: 규칙 적용 시 발생하는 예외 케이스를 식별하고 처리 방안을 결정한다.

---

## Requirements

### 요구사항 1: FTP 기반 TDoc 데이터 수집 (Stage 1: Collector)

**User Story:** 연구자로서 나는 3GPP FTP 서버에서 TDoc List를 자동으로 수집하고 싶다. 그래야만 최신 표준화 활동 데이터를 지속적으로 확보하여 분석에 활용할 수 있기 때문이다.

#### 수락 기준

1. THE Collector SHALL 3GPP FTP 서버에서 TDoc List xlsx 파일을 탐색하고, 로컬 `data/raw/`에 존재하지 않는 파일을 다운로드한다.
2. THE Collector SHALL 파일명 패턴에서 TSG, WG, 회차(MTG) 정보를 추출한다.
3. THE Collector SHALL 수집 대상 TSG, WG, 시작 회차 등 수집 범위를 `config/collector.yaml`에서 읽어 적용한다.
4. IF 다운로드 대상 파일이 이미 로컬에 존재하는 경우, THEN THE Collector SHALL 해당 파일을 재다운로드하지 않는다.
5. WHEN 파일 다운로드가 실패하는 경우, THE Collector SHALL 실패 원인과 파일 경로를 로그에 기록하고 설정된 재시도 횟수만큼 재시도한다.
6. WHEN 최대 재시도 횟수를 초과하는 경우, THE Collector SHALL 해당 파일을 실패 목록에 등록하고 다음 파일 수집을 계속 진행한다.
7. THE Collector SHALL 수집 파일명, 수집 일시, 성공/실패 여부를 수집 이력 로그에 기록한다.

#### 데이터 기반 규칙 도출 영역

- **수집 시작 회차**: FTP 서버의 디렉토리 구조를 분석하여 유효한 TDoc List 파일이 존재하는 최소 회차를 결정한다.
- **파일명 패턴**: 실제 FTP 서버의 파일명 패턴을 분석하여 파싱 규칙을 도출한다.

#### 참고 (기존 분석 규칙 — 2026-09 원본 노트북 재검증 완료)

- FTP 경로: `ftp.3gpp.org` 서버 하위 `/tsg_{tsg}/TSG_{TSG}/TSGR_{mtg}/Docs/` (예: `/tsg_ran/TSG_RAN/TSGR_69/Docs`). TSG 총회(Plenary)뿐 아니라 WG1~WG6 하위 워킹그룹 디렉토리도 동일 패턴으로 수집 대상이므로, `config/collector.yaml`의 `targets`에는 WG 단위 설정이 함께 필요하다.
- 수집 시작 회차: TSG 69회차 이상 (이전 회차는 TDoc List 형식이 상이)
- 파일명 패턴: `TDoc_List_Meeting_{TSG}#{MTG_NUM}.xlsx`. e-meeting(코로나 시기 등)은 `#{MTG_NUM}-e.xlsx`처럼 접미사가 붙을 수 있으므로, MTG 추출은 `#(\d+)` 정규식으로 접미사와 무관하게 숫자만 취득해야 한다. 파일 판별 자체는 정확한 패턴 매칭이 아니라 `'TDoc_List' in filename and filename.endswith('.xlsx')` 형태의 느슨한 매칭이었다.
- **재시도/실패 목록/로컬 파일 존재 시 스킵 로직(수락 기준 1.4~1.7)은 원본 노트북에 존재하지 않는 신규 자동화 요구사항이다.** 원본은 `try/except`로 에러를 출력만 하고 재시도·이력 관리가 없었다. 안정적 운영을 위해 본 시스템에서 새로 설계한 것이며 "기존 분석 규칙"이 아님을 명확히 한다.

---

### 요구사항 2: TDoc 메타데이터 파싱 (Stage 1.5: Parser)

**User Story:** 연구자로서 나는 TDoc List xlsx 파일을 일관되게 파싱하고 싶다. 그래야만 TSG별·회차별로 형식이 다소 상이한 xlsx 파일도 표준화된 형태로 처리할 수 있기 때문이다.

#### 수락 기준

1. THE Parser SHALL TDoc List xlsx 파일에서 TDoc, Title, Source, Related WIs, Release, Uploaded 컬럼을 파싱하여 표준화된 DataFrame으로 변환한다.
2. THE Parser SHALL Release 컬럼에서 정수 릴리즈 번호를 추출한다.
3. THE Parser SHALL 파일명에서 추출한 TSG, WG, MTG(회차) 정보를 각 행에 추가한다.
4. IF 필수 컬럼(TDoc, Title, Source)이 누락된 경우, THEN THE Parser SHALL 해당 파일명과 누락 컬럼 목록을 로그에 기록하고 해당 파일을 건너뛴다.
5. WHEN 파일명이 설정된 패턴에 맞지 않는 경우, THE Parser SHALL 해당 파일을 건너뛰고 경고 로그를 기록한다.
6. THE Parser SHALL 파싱된 DataFrame을 Parquet 형식으로 직렬화하고, 역직렬화한 결과가 원본과 동등함을 보장한다 (round-trip 속성).

#### 데이터 기반 규칙 도출 영역

- **컬럼 매핑**: TSG별로 컬럼명이 상이할 수 있으므로, 실제 데이터를 분석하여 컬럼 매핑 규칙을 도출한다.
- **Release 파싱 패턴**: "Rel-15", "Release 16", "R15" 등 다양한 표기법을 분석하여 파싱 규칙을 도출한다.

#### 참고 (기존 분석 규칙 — 2026-09 원본 노트북 재검증 완료)

- 실제 병합 데이터는 `TSG, WG, Uploaded, Source, Related WIs, MTG, Release, TDoc, Title` 9개 컬럼만 존재한다. **`Type` 컬럼은 원본 데이터에 근거가 없어 파싱 대상에서 제외한다** (실제 raw xlsx에서 추후 확인되면 재추가).
- Release 파싱: 원본은 `str.extract(r'(\d+)')`로 문자열 내 첫 숫자를 그대로 추출하며 "Rel"/"Release" 등 접두 텍스트는 전혀 확인하지 않는다. 예: "Rel-15" → 15, "Release 16" → 16, "R17" → 17, "rel15" → 15 (형식과 무관하게 첫 숫자만 추출). 단 숫자가 여러 개 섞인 문자열에서는 의도치 않은 값이 추출될 위험이 있으므로 실제 데이터로 별도 검증이 필요하다.

---

### 요구사항 3: Title 기반 필터링 (Stage 2: Title Filter)

**User Story:** 연구자로서 나는 분석 대상이 아닌 기고서 유형을 식별하고 제외하고 싶다. 그래야만 기업 간 실질적 기술 협력 관계만을 분석할 수 있기 때문이다.

#### 수락 기준

1. THE Preprocessor SHALL Title 컬럼을 분석하여 분석 대상에서 제외할 기고서 유형의 패턴을 식별한다.
2. THE Preprocessor SHALL `config/preprocessing.yaml`의 `title_exclude_patterns` 설정에 정의된 패턴과 일치하는 기고서를 분석 대상에서 제외한다.
3. THE Preprocessor SHALL 패턴 매칭 시 대소문자를 무시한다 (case-insensitive).
4. THE Preprocessor SHALL 제외된 기고서 수와 제외 사유별 통계를 로그에 기록한다.

#### 데이터 기반 규칙 도출 영역

- **제외 패턴 목록**: Title 데이터를 분석하여 Liaison Statement, CR Pack 등 분석 제외 대상 패턴을 도출한다.
- **패턴 영향도**: 각 패턴이 제외하는 레코드 수를 측정하여 규칙의 적절성을 검증한다.

#### 참고 (기존 분석 규칙)

제외 대상 패턴 예시 (12개 LS 관련 패턴 + CR pack, 2026-09 원본 노트북 재검증 결과 정확히 일치):
- `LS on`, `LS to`, `LS Reply`, `Reply LS`, `LS in relation to`, `LS for`, `LS regarding`, `LS response`, `LS out`, `LS answer`, `LS about`, `LS-Replay`, `CR pack`
- 참고: 원본 노트북 실측 영향도 — 전체 584,411행 중 LS 패턴으로 31,746건, CR pack으로 2,503건 제외됨.

---

### 요구사항 4: Source 정규화 및 기업 추출 (Stage 3: Membership-based Extraction)

**User Story:** 연구자로서 나는 TDoc Source 문자열에서 실제 기업명만을 정확하게 추출하고 정규화하고 싶다. 그래야만 네트워크 분석에서 기업 노드가 중복되지 않고, 비기업 주체(의장, 서기 등)가 자동으로 제외되기 때문이다.

#### 수락 기준

1. THE Preprocessor SHALL 전체 Source 문자열에서 ETSI 멤버십 기업명을 직접 탐색하여 추출한다.
2. THE Preprocessor SHALL Source 문자열 탐색 전에 Source 문자열 정제 규칙을 적용한다.
3. THE Preprocessor SHALL 멤버십 기업명 탐색 시 멤버십 정규화 규칙을 순차적으로 적용하여 단순화된 이름으로 매칭한다.
4. THE Preprocessor SHALL 탐색 시 대소문자를 무시한다 (case-insensitive).
5. THE Preprocessor SHALL 수작업 매핑 파일(`data/reference/company_manual_mapping.xlsx`)의 별칭(alias)을 멤버십 목록에 포함하여 탐색한다.
6. WHEN Source에서 추출된 기업이 0개인 경우, THE Preprocessor SHALL 해당 Source를 `data/reference/unmatched_sources.csv`에 기록한다.
7. THE Preprocessor SHALL 추출된 기업명 목록을 개별 행으로 분리(explode)한다.
8. THE Preprocessor SHALL 추출/분리 전후 레코드 수 변화를 로그에 기록한다.
9. THE Preprocessor SHALL 매핑 결과를 캐시로 저장하며, 입력 Source 목록의 해시가 변경될 때 캐시를 무효화한다.

#### 멤버십 기반 추출 로직

```
입력: "Samsung Electronics Co., Ltd., Nokia, Chair"
  ↓ Source 문자열 정제 (대괄호, 마침표 제거, 앞뒤 공백 추가)
  ↓ 멤버십 기반 추출 (정규화된 멤버십 기업명으로 직접 탐색)
출력: ["Samsung Electronics", "Nokia"]
  → "Chair"는 멤버십에 없으므로 자동 제외
  → "Ltd." 잘못 분리 문제 원천 해결
```

#### Source 문자열 정제 규칙 (매칭 전 전처리)

Source 문자열에서 멤버십 기업명을 탐색하기 전에 다음 정제 규칙을 적용한다:

1. **CMCC 예외처리**: `CMCC` → `China Mobile` 변환 (MCC 필터링 전 예외처리)
2. **대괄호 제거**: `[`, `]` 문자 제거
3. **마침표 제거**: `.` 문자 제거
4. **단어 경계 추가**: 앞뒤 공백 추가 후 매칭 (부분 문자열 오매칭 방지)

#### 멤버십 정규화 규칙 (순차 적용)

ETSI 멤버십 목록의 기업명을 다음 규칙을 **순서대로** 적용하여 정규화한다. 모든 규칙은 `config/preprocessing.yaml`의 `membership_normalization` 섹션에서 관리한다.

**a) stopwords 제거 (법인격 + 일반 단어) - 62개 (2026-09 원본 노트북 재검증 결과 정정)**

법인격 표기 및 일반적인 기업명 접미사를 제거한다:
- **법인격 (47개)**: `GmbH & Co.KG`, `GmbH`, `SA/NV`, `Corporation.`, `Corporation`, `Corp.`, `Corp`, `Limited`, `Co. Ltd.`, `Co. Ltd`, `Co Ltd.`, `Co Ltd`, `Co.`, `Co `, `Intl Ltd.`, `Intl Ltd`, `UK Ltd.`, `UK Ltd`, `UK Limited`, `International`, `Pvt`, `Ltd.`, `Ltd`, `Incorporated`, `Inc.`, `Inc`, `B.V.`, `B.V`, `S.A.S.`, `S.A.S`, `SAS`, `S.A.`, `S.A`, `S.L.`, `A.S.`, `S.p.A.`, `SpA`, `LLC`, `Company`, `N.V.`, `AB`, `A/S`, `ASA`, `AS`, `AG`, `plc`, `s.r.o`
- **일반 단어 (15개)**: `Software Technology`, `Software Tech.`, `Technology`, `Technologies`, `Tech.`, `Mobile Communication`, `Mobile comm.`, `Communication`, `Com.`, `Com `, `Satellite`, `Computer`, `R&D`, `Mobility`, `MS`

**b) countries 제거 (국가명 suffix) - 23개 (2026-09 원본 노트북 재검증 결과 정정)**

기업명 뒤에 붙는 국가명 접미사를 제거한다:
`Germany`, `FRANCE`, `Belgium`, `Italia`, `Denmark`, `Spain`, `Sweden`, `Switzerland`, `Benelux`, `Hungary`, `Deutschland`, `Finland`, `Polska`, `Austria`, `España`, `Europe`, `Romania`, `UK`, `Japan`, `India`, `Ireland`, `USA`, `Korea`

**c) removes 제거 (지명) - 4개**

기업명에 포함된 지명을 제거한다:
`Beijing`, `Nanjing`, `Chengdu`, `Telecommunications Cor`

**d) replaces 특수 매핑 - 15개 (2026-09 원본 노트북 재검증 결과 정정)**

특정 기업명을 표준화된 이름으로 변환한다:

| 원본 | 변환 후 |
|------|---------|
| `Guangdong OPPO` | `OPPO` |
| `Chinatelecom` | `China Telecom` |
| `DOCOMO` | `NTT Docomo` |
| `NTT` | `NTT Docomo` |
| `GW` | `Greenerwave` |
| `GM - ATCI` | `GM` |
| `HuaWei` | `Huawei` |
| `Huawei Device` | `Huawei` |
| `IBM Europe` | `IBM` |
| `Indian Institute of Tech (M)` | `IIT Madras` |
| `Indian Institute of Tech (H)` | `IIT Hyderabad` |
| `L.M. Ericsson` | `Ericsson` |
| `Security Service` | `Swedish Security Service` |
| `Telekom` | `Deutsche Telekom` |
| `Deutsche Deutsche` | `Deutsche` |

**e) brackets 괄호 제거**

`(...)` 형태의 괄호와 그 이후 내용을 제거한다. 구현은 `re.split(r'\s\(', name)[0]`처럼 여는 괄호(및 앞 공백) 기준으로 잘라내는 방식을 권장한다. (원본 노트북의 매칭 마스크 `str.contains(r'|\(.*?\)')`는 선행 빈 alternation으로 인해 모든 문자열이 True로 매치되는 결함이 있었으므로 그대로 재현하지 않는다.)

**f) startswith 통합**

정렬 후 이전 기업명으로 시작하는 기업명을 이전 값으로 통합한다.
- **예외 목록**: `BTL`, `CISA ECD`, `Intelsat`, `IIIT Bangalore` (통합하지 않음)

**g) suffix 제거 (접미어) - 54개**

기업명 뒤에 붙는 일반적인 접미어를 제거한다:
`system`, `Web Services`, `Software`, `Systems`, `Wireless`, `University`, `Networks`, `Network`, `Research`, `advanced`, `Satcom`, `Techno-Solutions`, `Devices`, `Veritas ADT`, `Design`, `ECD`, `IOD`, `Aerospace`, `Digital`, `Automotive`, `Licensing`, `innovations`, `innovation`, `Compliancy Solutions`, `Solutions`, `TrafficCom`, `Transportation`, `Global`, `Micro`, `Secure`, `Niedersachsen`, `DE L'INTERIEUR`, `Manufacturing`, `Electric Industry`, `Industries`, `Semiconductors`, `Semiconductor`, `Media`, `laboratory`, `Labs`, `Lab`, `Neuchatel SA`, `electronic SE`, `-`, `Consulting`, `Consultant`, `Elec. Industries`, `NRTA`, `Motor`, `Consult Services`, `Recherche et Développement`, `IoT`, `-Telecom`, `Integr. Circuit`

**h) prefix 제거 (접두어) - 8개**

기업명 앞에 붙는 지명 접두어를 제거한다:
`Hangzhou `, `IIIT `, `IIT `, `Institute `, `Institut `, `Shanghai `, `ShenZhen `, `Wuhan `

**구조 결정 (2026-09 스펙 검수 반영)**: 원본 노트북은 g)·h) 단계를 a)~f) 결과 컬럼과 별도로 복사한 컬럼에 적용하는 구조였다(하나의 연속 파이프라인이 아니라 두 갈래로 분기된 파생 컬럼). 이는 반복 실험 과정에서 생긴 우연적 구조로 판단되며, 본 시스템은 a)~h) 8단계를 **하나의 값에 순서대로 누적 적용하는 단일 연속 파이프라인**으로 구현한다 (설계 단순성 및 유지보수성을 위한 의도적 결정).

#### 정규화 적용 예시

```
원본 멤버십: "Guangdong OPPO Mobile Communication Co., Ltd. (Shenzhen)"
  ↓ a) stopwords 제거: "Guangdong OPPO Mobile (Shenzhen)"
  ↓ d) replaces 적용: "OPPO Mobile (Shenzhen)"
  ↓ e) brackets 제거: "OPPO Mobile"
  ↓ g) suffix 제거: "OPPO"
정규화 결과: "OPPO"
```

#### 데이터 기반 규칙 도출 영역

- **정규화 규칙 목록**: 실제 Source 데이터와 ETSI 멤버십에서 패턴을 분석하여 각 규칙의 항목을 도출한다.
- **약어/오타 교정 딕셔너리**: 빈출 약어 및 오타 패턴을 분석하여 수작업 매핑 파일에 등록한다.
- **미매칭 Source 분석**: `unmatched_sources.csv`를 분석하여 추가 alias 등록이 필요한 기업을 식별한다.
- **영향도 분석**: 각 정규화 단계별 고유 기업 수 변화를 측정하여 규칙의 효과를 검증한다.

#### 구현 참고 사항 (2026-09 스펙 검수 반영)

- **수작업 매핑 파일**: 원본 노트북에는 `company_manual_mapping.xlsx`가 존재하지 않는다. 유사한 역할을 한 원본 파일은 `3GPPMembership_company_edit.xlsx`(미매칭 약어를 수동 편집)이며, 본 요구사항은 이를 참고하여 alias 매핑을 명시적 파일 형태로 재설계한 것이다.
- **캐시(4.9)와 요구사항 7.2 캐시의 관계**: 본 요구사항의 캐시는 "입력 Source 목록의 해시"를 키로 하는 MembershipExtractor 전용 매핑 캐시이며, 요구사항 7.2의 `CacheManager`(입력 파일 수정 시각 기반, 파이프라인 단계 전체 캐시)와는 별개 메커니즘이다. `MembershipExtractor`는 `CacheManager`를 재사용하되 캐시 키 생성 전략만 다르게 적용한다 (design.md 참조).

#### 참고 (기존 분석 방식 및 문제점 — 2026-09 원본 노트북 재검증 완료)

**기존 3단계 방식:**
1. Source Explode: `re.split(',|;', Source)`로 분리
2. Source Filter: CHAIR, VC, TSG, PLENARY, RAN\d, SA\d, CT\d, WG, MCC 등 비기업 패턴 제거 (CMCC→China Mobile 예외 처리 포함)
3. Membership Matching: 공백 패딩된 멤버십 기업명에 대한 **정확한 부분 문자열(substring) 매칭** (`str.contains()`). rapidfuzz 등 fuzzy-matching 라이브러리는 사용되지 않았다 (스펙 초안의 "rapidfuzz" 서술은 사실 오류로 정정).

**기존 문제점:**
- 중복 매칭 발생으로 87,350건 drop_duplicates 필요 (실측: 846,027건 매칭 → 758,677건으로 축소, 검증 완료)
- 약어 기업(CATR, UIC, TDIA 등) 수동 등록 필요
- 법인격 표기 내 콤마로 인한 분리 오류 가능성 존재 (예: "Motorola Solutions, Inc." → ["Motorola Solutions", "Inc."]). 다만 구체적 손실 건수("9,461건")는 원본 노트북에서 재확인되지 않아 근거 불명확한 수치로 판단, 참고용 예시로만 남긴다.

**개선:**
- 멤버십 기반 추출로 분리/필터/매칭 3단계를 1단계로 통합
- 법인격 내 콤마 문제 원천 해결
- 비기업(Chair, MCC, Rapporteur 등)은 멤버십에 없으므로 자동 제외

#### 참고 (정규화 단계별 영향도 - 기존 분석 결과)

| 단계 | 고유 기업 수 | 감소 |
|------|-------------|------|
| 원본 멤버십 | 789 | - |
| unique members | 787 | -2 |
| stopwords split | 737 | -50 |
| countries split | 668 | -69 |
| stopwords removed | 662 | -6 |
| exception replaced | 659 | -3 |
| bracket split | 648 | -11 |
| startswith concat | 582 | -66 |

---

### 요구사항 5: Work Item Explode (Stage 4: WI Explode)

**User Story:** 연구자로서 나는 복수 Work Item이 연결된 기고서를 개별 Work Item 단위로 분리하고 싶다. 그래야만 Work Item별 기업 참여 현황을 정확하게 집계할 수 있기 때문이다.

#### 수락 기준

1. THE Preprocessor SHALL Related WIs 컬럼을 분석하여 Work Item 구분자 패턴을 식별한다.
2. THE Preprocessor SHALL `config/preprocessing.yaml`의 `wi_delimiters` 설정에 정의된 구분자로 Work Item을 개별 행으로 분리(explode)한다.
3. THE Preprocessor SHALL `config/preprocessing.yaml`의 `wi_exclude_patterns` 설정에 정의된 패턴과 일치하는 Work Item을 분석 대상에서 제외한다.
4. THE Preprocessor SHALL 분리 전후 레코드 수 변화와 제외된 Work Item 통계를 로그에 기록한다.

#### 데이터 기반 규칙 도출 영역

- **구분자 패턴**: Related WIs 데이터를 분석하여 구분자(쉼표, 세미콜론 등)를 식별한다.
- **제외 대상 WI**: TEI, DUMMY 등 분석에 무의미한 Work Item 패턴을 식별한다.

#### 참고 (기존 분석 규칙 — 2026-09 원본 노트북 재검증 완료)

- 구분자: 쉼표(,)
- 제외 패턴: `TEI`, `DUMMY` — **원본 노트북은 `r'TEI|DUMMY'`를 `str.contains(..., flags=re.IGNORECASE)`로 적용하는 부분 문자열(substring) 매칭이며, 접두어 고정(`^`)이 아니다.** 스펙 초안에서 `^TEI`, `^DUMMY`(접두어 고정)로 잘못 명시되었던 것을 원본과 일치하도록 정정한다 (config 예시 참고). 매칭은 대소문자를 무시한다(case-insensitive).

---

### 요구사항 6: 시간 정보 추가 (Stage 5: Temporal Enrichment)

**User Story:** 연구자로서 나는 기고서에 시간 정보(연도, 분기, Release)를 추가하고 싶다. 그래야만 시간에 따른 협력 구조 변화를 분석할 수 있기 때문이다.

#### 수락 기준

1. THE Preprocessor SHALL Uploaded 날짜 컬럼으로부터 Year, Quarter 컬럼을 생성한다.
2. THE Preprocessor SHALL `config/preprocessing.yaml`의 `date_range` 설정에 정의된 범위를 벗어나는 날짜를 분석 대상에서 제외한다.
3. THE Preprocessor SHALL 제외된 레코드 수와 제외 사유를 로그에 기록한다.

#### 데이터 기반 규칙 도출 영역

- **유효 날짜 범위**: Uploaded 날짜 분포를 분석하여 이상치(오류 데이터)를 식별하고 유효 범위를 결정한다.

#### 참고 (기존 분석 규칙 — 2026-09 원본 노트북 재검증 완료)

- 제외 범위: 2015년 이전 (날짜 오류 2건 발견, 실측 오류 연도: 1999년)
- Quarter 계산 로직은 원본 노트북에 존재하지 않는다 (신규 도출). 월 기준 표준 분기 매핑(1-3월: Q1, 4-6월: Q2, 7-9월: Q3, 10-12월: Q4)을 신규로 채택한다.
- 참고: Edge 생성 단계(Stage 6) 원본 노트북에는 `2016 < year < 2024`라는 추가 연도 상한 필터가 별도로 존재했으나, 이는 분석 시점(2024년) 기준 "그때까지 수집된 데이터 범위"를 반영한 일시적 제약으로 판단되어 본 시스템에는 이식하지 않는다. 최소 연도(2015) 제외만 영구 규칙으로 유지한다.

---

### 요구사항 7: 전처리 결과 저장 및 캐싱

**User Story:** 연구자로서 나는 전처리 결과를 효율적으로 저장하고 재사용하고 싶다. 그래야만 반복 실행 시 불필요한 재처리를 피할 수 있기 때문이다.

#### 수락 기준

1. THE Preprocessor SHALL 전처리 결과를 Parquet 형식으로 `data/interim/` 디렉토리에 저장한다.
2. THE Preprocessor SHALL 입력 파일의 수정 시각이 변경되지 않은 경우, 재실행 시 전처리 단계를 건너뛰고 캐시를 재사용한다.
3. THE Preprocessor SHALL 각 전처리 단계별 적용된 규칙과 영향도(제거/변환된 레코드 수)를 메타데이터로 기록한다.

---

### 요구사항 8: 기업 간 협력 네트워크 구성 (Stage 6: Company Network)

**User Story:** 연구자로서 나는 Work Item을 매개로 한 기업 간 공동 기고 관계를 네트워크로 구성하고 싶다. 그래야만 표준화 협력 구조를 정량적으로 분석할 수 있기 때문이다.

#### 수락 기준

1. THE Network_Builder SHALL 동일 Work Item에 기고한 기업들의 모든 쌍(combination)을 Edge로 생성한다.
2. THE Network_Builder SHALL 동일 Work Item 내에서 하나의 기업은 1회만 집계하며(drop_duplicates), (A,B)와 (B,A)는 동일 Edge로 정규화한다.
3. THE Network_Builder SHALL 두 기업이 함께 기고한 Work Item의 고유 개수를 Edge Weight로 계산한다.
4. THE Network_Builder SHALL TSG 그룹(ALL/RAN/SA/CT) × 시간 단위(연도/Release/분기) × Weight threshold 조합별로 Edge list를 생성한다.
5. WHEN Weight threshold가 설정된 경우, THE Network_Builder SHALL Edge Weight가 threshold 이하인 Edge를 제거한다.
6. THE Network_Builder SHALL 생성된 Edge list를 Parquet 형식으로 `data/processed/` 디렉토리에 저장한다.

#### 참고 (기존 분석 규칙 — 2026-09 원본 노트북 재검증 완료)

- Edge 생성: `itertools.combinations` 사용. 원본은 Work Item별로 정렬 후 그룹화하여 Source<Target을 사실상 보장하는 방식이었으나, 본 시스템은 이를 `sorted(pair)`로 **명시적으로** 정규화하여 원본보다 견고하게 구현한다.
- 원본 파일 저장 형식은 CSV였으며(`{tsg}_{year}_{i}.csv`, 예: `ALL_2017_0.csv`), Parquet 저장과 `company_{tsg}_{time_unit}_{time_value}_{threshold}.parquet` 명명 규칙은 **본 시스템에서 새로 도입하는 설계 결정**이다 ("기존 분석 규칙"이 아님).
- **중요**: 원본 노트북은 실제로 `time_unit=year`만 사용했으며 `release`/`quarter` 단위 Edge 생성은 한 번도 실행된 적이 없다(변수만 정의되고 미사용). threshold도 사실상 0(필터 없음) 외에는 실행 이력이 없다. 즉 `time_units: [year, release, quarter]` × `thresholds: [0..9]` 전체 조합은 검증되지 않은 신규 확장 범위이며, 요구사항 16.1(30분 성능 예산) 산정 시 이 점을 반드시 고려해야 한다.

---

### 요구사항 9: Work Item 간 협력 네트워크 구성 (Stage 6: WI Network)

**User Story:** 연구자로서 나는 동일 기업이 기고한 Work Item들 간의 관계를 네트워크로 구성하고 싶다. 그래야만 표준화 활동에서 기술 영역 간 연계 구조를 파악할 수 있기 때문이다.

#### 수락 기준

1. THE Network_Builder SHALL 동일 기업이 기고한 Work Item들의 모든 쌍(combination)을 Edge로 생성한다.
2. THE Network_Builder SHALL (A,B)와 (B,A)를 동일 Edge로 정규화하고 중복을 제거한다.
3. THE Network_Builder SHALL 두 Work Item에 동시에 기고한 고유 기업 수를 Edge Weight로 계산한다.
4. THE Network_Builder SHALL 요구사항 8과 동일한 TSG × 시간 단위 × threshold 조합을 지원한다.
5. THE Network_Builder SHALL WI-to-WI Edge list를 요구사항 8과 동일한 파일 네이밍 패턴으로 저장한다.

---

### 요구사항 10: 네트워크 기본 통계 계산 (Stage 7: Statistics)

**User Story:** 연구자로서 나는 구성된 네트워크의 구조적 특성을 수치로 확인하고 싶다. 그래야만 연도별·Release별 협력 구조의 변화를 정량적으로 비교할 수 있기 때문이다.

#### 수락 기준

1. THE Network_Analyzer SHALL 각 네트워크에 대해 다음 지표를 계산한다:
   - 노드 수(nodes), Edge 수(edges), 가중 Edge 합계(weighted_edges)
   - 평균 연결 수(avg_degree), 평균 가중 연결 수(avg_weighted_degree)
   - 밀도(density), 연결 컴포넌트 수(connected_components)
   - 최장 최단 경로(diameter), 평균 경로 길이(avg_path_length)
   - 모듈성(modularity), 평균 군집 계수(avg_clustering_coefficient)
2. THE Network_Analyzer SHALL diameter와 avg_path_length를 가장 큰 연결 컴포넌트(LCC) 기준으로 계산한다.
3. IF LCC 노드 수가 2개 미만인 경우, THEN THE Network_Analyzer SHALL diameter와 avg_path_length를 null로 기록하고 경고 로그를 남긴다.
4. THE Network_Analyzer SHALL 계산된 통계를 CSV 및 Parquet 형식으로 저장한다.

#### 참고 (기존 분석 규칙 — 2026-09 원본 노트북 재검증 완료)

- 원본 노트북은 LCC 노드 수 2개 미만 상황에 대한 방어 로직이 없어 실제로는 예외가 발생하며 크래시한다. 수락 기준 3의 null 처리는 본 시스템에서 새로 추가하는 안정성 로직이다.
- 원본 노트북에서 modularity는 이 단계(기본 통계) 함수 내부에서 Louvain 커뮤니티 탐지를 인라인으로 실행하여 얻는 부산물이다. 본 시스템은 Louvain을 중복 실행하지 않도록, Stage 7 내에서 커뮤니티 탐지(요구사항 11)를 먼저 수행하고 그 결과(modularity 포함)를 통계 계산(본 요구사항)이 재사용하도록 구현 순서를 조정한다 (design.md 참조).

---

### 요구사항 11: 중심성 및 커뮤니티 분석 (Stage 7: Centrality & Community)

**User Story:** 연구자로서 나는 네트워크 내 주요 기업과 커뮤니티 구조를 파악하고 싶다. 그래야만 표준화 활동에서 핵심 참여자와 협력 클러스터를 식별할 수 있기 때문이다.

#### 수락 기준

1. THE Network_Analyzer SHALL 각 네트워크의 모든 노드에 대해 다음 **비가중(unweighted)** 중심성을 계산한다: Degree Centrality, Betweenness Centrality, Closeness Centrality, Eigenvector Centrality. (Edge Weight는 네트워크 구성 단계의 threshold 필터링에만 사용하며 중심성 계산 자체에는 반영하지 않는다 — 원본 노트북과 동일한 방식이다. 가중 중심성 도입은 결과 해석에 영향을 주는 별도 설계 결정이 필요하므로 향후 개선 과제로 남긴다.)
2. THE Network_Analyzer SHALL 모든 Centrality 값을 0~1 사이로 정규화한다.
3. WHEN Eigenvector Centrality 계산이 1,000회 반복 내에 수렴하지 않는 경우, THE Network_Analyzer SHALL 해당 값을 null로 기록하고 경고 로그를 남긴다.
4. THE Network_Analyzer SHALL Louvain 알고리즘을 random_seed 고정하여 커뮤니티를 탐지한다.
5. THE Network_Analyzer SHALL 각 노드의 커뮤니티 ID와 커뮤니티별 노드 목록을 기록한다.
6. THE Network_Analyzer SHALL 중심성 및 커뮤니티 분석 결과를 Parquet 형식으로 저장한다.

#### 참고 (기존 분석 규칙 — 2026-09 원본 노트북 재검증 완료)

- **Louvain seed=42는 원본 노트북에 존재하지 않는다.** 원본은 `python-louvain`(`community_louvain.best_partition`)을 사용하되 `randomize=True`로 의도적 비결정 실행을 했으며, seed 관련 인자를 전혀 지정하지 않았다(전체 코드에서 seed=42 사용 흔적 없음). seed 고정은 요구사항 16.2(재현성)를 만족하기 위해 **본 시스템에서 새로 도입하는 설계 결정**이며, 원본 분석 결과와 동일한 커뮤니티 구조를 재현하지는 않는다.
- 라이브러리는 `python-louvain`(`community_louvain.best_partition(G, random_state=42)`) 사용을 권장한다. NetworkX 3.x 네이티브 `nx.community.louvain_communities`는 반환 형식(노드 집합 리스트 vs 노드→ID 딕셔너리)이 달라 하위 처리 로직에 영향을 주므로, 구현 시 택일하여 design.md에 명시한다.
- Eigenvector max_iter=1000은 원본(NetworkX 기본값 100)보다 완화한 값이며 본 시스템에서 새로 정한 값이다. 원본은 미수렴 예외(`PowerIterationFailedConvergence`)를 처리하지 않아 실제로 크래시했으므로, 수락 기준 3의 null 처리는 신규 방어 로직이다.

---

### 요구사항 12: 고급 네트워크 분석 (Stage 7: Advanced Analysis)

**User Story:** 연구자로서 나는 네트워크의 스케일프리 특성, 스몰월드 특성, 핵심 구조를 검증하고 싶다. 그래야만 3GPP 협력 네트워크의 이론적 특성을 실증적으로 뒷받침할 수 있기 때문이다.

#### 수락 기준

**적용 범위 (2026-09 스펙 검수 반영)**: 본 요구사항(고급 분석)은 계산 비용이 높아 요구사항 8~11과 달리 **모든 TSG × 시간단위 × threshold 조합에 대해 실행하지 않는다.** 아래 1~4번 항목은 TSG 그룹 × 연도(time_unit=year) × threshold=0(필터 없음) 조합에 대해서만 실행하며, 민감도 분석(5번)만 threshold 0~9를 스윕하되 대표 시간 값(예: 최신 연도 또는 ALL 기간 집계)에 한정한다. Release/Quarter 단위 및 threshold>0 조합에는 1~4번 고급 분석을 적용하지 않는다. (원본 노트북도 threshold 스윕이나 release/quarter 단위 고급 분석을 실행한 이력이 없으므로, 이 범위 제한은 요구사항 16.1의 30분 성능 예산을 지키기 위한 신규 설계 결정이다.)

1. THE Network_Analyzer SHALL Degree 분포의 Power-law 적합성을 검증하고 지수(exponent) 값과 p-value를 계산한다. (p-value는 `powerlaw` 패키지의 `Fit.distribution_compare()` 등 별도 API 호출이 필요하다. 원본 노트북은 exponent만 계산했다.)
2. THE Network_Analyzer SHALL 동일 크기의 Erdős–Rényi 무작위 네트워크를 생성하여 Small-world 지수 σ = (C/C_rand)/(L/L_rand)를 **실제로 계산**한다 (C=군집계수, L=평균 경로 길이, `_rand`는 무작위 네트워크 기준값). 원본 노트북은 무작위 네트워크의 C, L을 나란히 출력만 했을 뿐 σ 비율 자체는 계산한 적이 없으므로, 이 항목은 전적으로 신규 구현이다. `nx.sigma()`는 대규모 그래프에서 성능이 매우 느린 것으로 알려져 있으므로, `config/analysis.yaml`의 `random_network_samples`로 무작위 네트워크 생성 횟수를 조절 가능한 커스텀 구현을 사용한다.
3. THE Network_Analyzer SHALL Edge의 weight 기준 Maximum Spanning Tree를 추출하여 핵심 협력 구조를 제공한다.
4. THE Network_Analyzer SHALL 동일 시간 단위 내 TSG 그룹별 Degree Centrality **순위(rank)** 간 Spearman 상관계수를 계산한다 (`scipy.stats.spearmanr` 또는 `.corr(method='spearman')` 사용). 원본 노트북은 순위가 아닌 원본 값에 대해 Pearson(`corr()` 기본값)을 사용한 오류가 있었으므로 그대로 재현하지 않는다.
5. THE Network_Analyzer SHALL threshold 0~9 각 단계에서 네트워크 지표 값을 기록한 민감도 분석 결과를 저장한다.

#### 제외 범위 (2026-09 스펙 검수 반영)

원본 논문 노트북에는 본 요구사항에 포함되지 않은 추가 분석(assortativity/k_nn 회귀, rich-club coefficient, Z-score 기반 edge 유의성 분석, TSG 간 Jaccard/weighted-Jaccard, 계층적(덴드로그램)·Girvan-Newman 커뮤니티 탐지 등)이 존재한다. 이들은 논문 단계의 탐색적 분석이며, 본 시스템은 지속 운영 가능한 핵심 지표 제공을 목표로 하므로 **의도적으로 제외**한다. 추후 필요 시 별도 요구사항으로 추가한다.

---

### 요구사항 13: 인터랙티브 대시보드 (Stage 8: Visualization)

**User Story:** 연구자로서 나는 분석 결과를 인터랙티브하게 탐색하고 싶다. 그래야만 다양한 조건 조합에서 협력 네트워크 구조의 변화를 직관적으로 이해할 수 있기 때문이다.

#### 수락 기준

1. THE Dashboard SHALL TSG 그룹, 시간 단위, 시간 범위, Weight threshold, 네트워크 유형을 선택하는 사이드바 필터 패널을 제공한다.
2. THE Dashboard SHALL 선택한 조건에 해당하는 네트워크 그래프를 Plotly를 통해 인터랙티브하게 표시한다.
   - 노드 크기: Degree에 비례
   - 노드 색상: 커뮤니티 구분
   - Edge 굵기: Weight에 비례
3. THE Dashboard SHALL 시간에 따른 네트워크 통계 변화를 라인 차트로 표시하며, TSG 그룹별 비교 뷰를 지원한다.
4. THE Dashboard SHALL 선택한 조건에서 상위 N개 노드의 Centrality 순위를 테이블로 표시하며, 노드 이름 검색 기능을 제공한다.
5. THE Dashboard SHALL 탐지된 커뮤니티 목록과 각 커뮤니티의 크기 및 주요 노드를 표시한다.
6. WHEN 선택한 조건에 해당하는 데이터가 없는 경우, THE Dashboard SHALL "데이터 없음" 메시지를 표시한다.
7. THE Dashboard SHALL `streamlit run src/dashboard/app.py` 명령으로 로컬 브라우저에서 접근 가능한 웹 인터페이스를 제공한다.

#### 참고 (기존 분석 방식)

- 기존: matplotlib 정적 그래프
- 개선: Plotly + Streamlit 인터랙티브 대시보드

---

### 요구사항 14: 파이프라인 자동 스케줄링

**User Story:** 연구자로서 나는 파이프라인이 주기적으로 자동 실행되기를 원한다. 그래야만 수작업 개입 없이 분석 데이터가 최신 상태로 유지되기 때문이다.

#### 수락 기준

1. THE Scheduler SHALL `config/pipeline.yaml`의 schedule 설정에 정의된 실행 주기에 따라 파이프라인을 자동으로 실행한다.
2. WHEN schedule 설정이 유효하지 않거나 누락된 경우, THE Scheduler SHALL 명확한 오류 메시지를 출력하고 종료한다.
3. WHEN 파이프라인 실행 중 예외가 발생하는 경우, THE Scheduler SHALL 발생 시각, 단계, 오류 원인을 로그에 기록하고 이후 예약된 실행을 계속 유지한다.
4. WHEN 파이프라인이 정상 완료된 경우, THE Scheduler SHALL 완료 시각과 실행된 단계 목록을 로그에 기록한다.

---

### 요구사항 15: 모듈성 및 설정 외부화

**User Story:** 연구자로서 나는 파이프라인의 각 단계를 독립적으로 실행하고, 파라미터를 코드 수정 없이 변경하고 싶다. 그래야만 실험 조건을 빠르게 변경하고 개별 모듈을 디버깅할 수 있기 때문이다.

#### 수락 기준

1. THE Pipeline SHALL Collector, Preprocessor, Network_Builder, Network_Analyzer, Dashboard를 독립적으로 실행 가능한 모듈로 분리한다.
2. THE Pipeline SHALL 각 모듈을 `python -m src.{module_name}` 형식으로 독립 실행할 수 있도록 한다.
3. THE Pipeline SHALL 모든 설정값(FTP 경로, 필터 패턴, threshold 등)을 `config/` 디렉토리의 YAML 파일에서 관리한다.
4. WHEN 새로운 TSG나 WG가 추가될 경우, THE Pipeline SHALL 설정 파일 수정만으로 대응 가능해야 하며 소스 코드 변경을 요구하지 않는다.

---

### 요구사항 16: 파이프라인 성능 및 재현성

**User Story:** 연구자로서 나는 파이프라인이 빠르고 재현 가능하게 실행되기를 원한다. 그래야만 분석 실험을 반복하고 결과를 검증할 수 있기 때문이다.

#### 수락 기준

1. THE Pipeline SHALL 수집을 제외한 전처리·네트워크 구성·분석 전 단계를 현재 데이터 기준으로 30분 이내에 완료한다.
2. THE Pipeline SHALL 동일한 입력 데이터와 설정 파일이 주어질 때, 항상 동일한 분석 결과를 생성한다 (재현성).
3. IF 네트워크 그래프가 표시 요청된 경우, THEN THE Dashboard SHALL 5초 이내에 로딩을 완료한다.

#### 참고 (2026-09 스펙 검수 반영)

원본 노트북은 본 요구사항이 가정하는 규모(TSG×연도/릴리즈/분기×threshold 전체 조합, 고급 분석 포함)를 실제로 실행해본 이력이 없다. 요구사항 12의 "적용 범위" 제한(대표 조합에 한정)은 이 성능 예산을 지키기 위한 전제 조건이므로, 구현 착수 전 대표 데이터셋으로 사전 프로파일링을 권장한다.

---

### 요구사항 17: 테스트 및 검증

**User Story:** 연구자로서 나는 파이프라인의 핵심 로직이 테스트되기를 원한다. 그래야만 코드 변경 시 기존 기능이 깨지지 않음을 확인할 수 있기 때문이다.

#### 수락 기준

1. THE Pipeline SHALL 핵심 전처리 로직(멤버십 기반 기업 추출, Edge list 생성)에 대해 pytest 기반 단위 테스트를 포함한다.
2. THE Pipeline SHALL 각 테스트를 모의(mock) 데이터셋으로 실행 가능하도록 한다.
3. THE Pipeline SHALL 주요 데이터 변환 함수에 대해 round-trip 테스트를 포함한다 (parse → format → parse 동등성).

---

## 설정 파일 구조 (참고)

```yaml
# config/collector.yaml
ftp:
  host: ftp.3gpp.org
  # 경로 패턴: /tsg_{tsg}/TSG_{TSG}/TSGR_{mtg}/Docs/ (TSG 총회) + WG 하위 디렉토리
  base_path_template: "/tsg_{tsg_lower}/TSG_{tsg}/TSGR_{mtg}/Docs/"
targets:
  - tsg: RAN
    min_meeting: 69
    wg_list: [TSG, WG1, WG2, WG3, WG4, WG5, WG6]
  - tsg: SA
    min_meeting: 69
    wg_list: [TSG, WG1, WG2, WG3, WG4, WG5, WG6]
  - tsg: CT
    min_meeting: 69
    wg_list: [TSG, WG1, WG2, WG3, WG4, WG5, WG6]
retry:
  max_attempts: 3
  delay_seconds: 5

# config/preprocessing.yaml
title_exclude_patterns:
  - "LS on"
  - "LS to"
  - "LS Reply"
  - "Reply LS"
  - "LS in relation to"
  - "LS for"
  - "LS regarding"
  - "LS response"
  - "LS out"
  - "LS answer"
  - "LS about"
  - "LS-Replay"
  - "CR pack"

# Source 문자열 정제 규칙 (매칭 전 전처리)
source_cleaning:
  special_replacements:
    CMCC: "China Mobile"
  remove_characters:
    - "["
    - "]"
    - "."
  add_word_boundary_spaces: true

# 멤버십 정규화 규칙 (순차 적용)
membership_normalization:
  # a) stopwords - 법인격 및 일반 단어 제거 (앞에 공백 포함)
  stopwords:
    # 법인격 (47개)
    - " GmbH & Co\\.KG"
    - " GmbH"
    - " SA/NV"
    - " Corporation\\."
    - " Corporation"
    - " Corp\\."
    - " Corp"
    - " Limited"
    - " Co\\. Ltd\\."
    - " Co\\. Ltd"
    - " Co Ltd\\."
    - " Co Ltd"
    - " Co\\."
    - " Co "
    - " Intl Ltd\\."
    - " Intl Ltd"
    - " UK Ltd\\."
    - " UK Ltd"
    - " UK Limited"
    - " International"
    - " Pvt"
    - " Ltd\\."
    - " Ltd"
    - " Incorporated"
    - " Inc\\."
    - " Inc"
    - " B\\.V\\."
    - " B\\.V"
    - " S\\.A\\.S\\."
    - " S\\.A\\.S"
    - " SAS"
    - " S\\.A\\."
    - " S\\.A"
    - " S\\.L\\."
    - " A\\.S\\."
    - " S\\.p\\.A\\."
    - " SpA"
    - " LLC"
    - " Company"
    - " N\\.V\\."
    - " AB"
    - " A/S"
    - " ASA"
    - " AS"
    - " AG"
    - " plc"
    - " s\\.r\\.o"
    # 일반 단어 (15개)
    - " Software Technology"
    - " Software Tech\\."
    - " Technology"
    - " Technologies"
    - " Tech\\."
    - " Mobile Communication"
    - " Mobile comm\\."
    - " Communication"
    - " Com\\."
    - " Com "
    - " Satellite"
    - " Computer"
    - " R&D"
    - " Mobility"
    - " MS"

  # b) countries - 국가명 suffix 제거 (앞에 공백 포함)
  countries:
    - " Germany"
    - " FRANCE"
    - " Belgium"
    - " Italia"
    - " Denmark"
    - " Spain"
    - " Sweden"
    - " Switzerland"
    - " Benelux"
    - " Hungary"
    - " Deutschland"
    - " Finland"
    - " Polska"
    - " Austria"
    - " España"
    - " Europe"
    - " Romania"
    - " UK"
    - " Japan"
    - " India"
    - " Ireland"
    - " USA"
    - " Korea"

  # c) removes - 지명 제거
  removes:
    - "Beijing"
    - "Nanjing"
    - "Chengdu"
    - "Telecommunications Cor"

  # d) replaces - 특수 매핑
  replaces:
    "Guangdong OPPO": "OPPO"
    "Chinatelecom": "China Telecom"
    "DOCOMO": "NTT Docomo"
    "NTT": "NTT Docomo"
    "GW": "Greenerwave"
    "GM - ATCI": "GM"
    "HuaWei": "Huawei"
    "Huawei Device": "Huawei"
    "IBM Europe": "IBM"
    "Indian Institute of Tech (M)": "IIT Madras"
    "Indian Institute of Tech (H)": "IIT Hyderabad"
    "L.M. Ericsson": "Ericsson"
    "Security Service": "Swedish Security Service"
    "Telekom": "Deutsche Telekom"
    "Deutsche Deutsche": "Deutsche"

  # e) brackets - 괄호 제거 패턴 (여는 괄호 기준 분리: re.split(brackets_pattern, name)[0])
  brackets_pattern: "\\s\\("

  # f) startswith - 통합 예외 목록
  startswith_exceptions:
    - "BTL"
    - "CISA ECD"
    - "Intelsat"
    - "IIIT Bangalore"

  # g) suffix - 접미어 제거 (앞에 공백 포함)
  suffix:
    - " system"
    - " Web Services"
    - " Software"
    - " Systems"
    - " Wireless"
    - " University"
    - " Networks"
    - " Network"
    - " Research"
    - " advanced"
    - " Satcom"
    - " Techno-Solutions"
    - " Devices"
    - " Veritas ADT"
    - " Design"
    - " ECD"
    - " IOD"
    - " Aerospace"
    - " Digital"
    - " Automotive"
    - " Licensing"
    - " innovations"
    - " innovation"
    - " Compliancy Solutions"
    - " Solutions"
    - " TrafficCom"
    - " Transportation"
    - " Global"
    - " Micro"
    - " Secure"
    - " Niedersachsen"
    - " DE L'INTERIEUR"
    - " Manufacturing"
    - " Electric Industry"
    - " Industries"
    - " Semiconductors"
    - " Semiconductor"
    - " Media"
    - " laboratory"
    - " Labs"
    - " Lab"
    - " Neuchatel SA"
    - " electronic SE"
    - " -"
    - " Consulting"
    - " Consultant"
    - " Elec\\. Industries"
    - " NRTA"
    - " Motor"
    - " Consult Services"
    - " Recherche et Développement"
    - " IoT"
    - "-Telecom"
    - " Integr\\. Circuit"

  # h) prefix - 접두어 제거 (뒤에 공백 포함)
  prefix:
    - "Hangzhou "
    - "IIIT "
    - "IIT "
    - "Institute "
    - "Institut "
    - "Shanghai "
    - "ShenZhen "
    - "Wuhan "

wi_delimiters:
  - ","

wi_exclude_patterns:  # 부분 문자열(substring) 매칭, case-insensitive (원본 노트북 검증 결과)
  - "TEI"
  - "DUMMY"

date_range:
  min_year: 2015

# config/network.yaml
thresholds: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
time_units: [year, release, quarter]
tsg_groups: [ALL, RAN, SA, CT]

# config/analysis.yaml
louvain_seed: 42
eigenvector_max_iter: 1000
random_network_samples: 100
```
