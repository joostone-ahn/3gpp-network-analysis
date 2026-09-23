# Implementation Plan: 3GPP Network Analysis Pipeline

## Overview

3GPP 표준화 기구의 TDoc 메타데이터를 수집·전처리하여 기업 간 협력 네트워크를 분석하는 Python 기반 파이프라인 시스템을 구축한다. 기존 Jupyter Notebook 코드 자산을 참조하되, 자동화·확장성·재현성을 갖춘 운영 가능한 시스템으로 재구성한다.

**구현 언어**: Python 3.10+

---

## Tasks

- [x] 1. 프로젝트 구조 및 설정 시스템 구축
  - [x] 1.1 프로젝트 디렉토리 구조 생성
    - `src/`, `config/`, `data/`, `tests/` 디렉토리 생성
    - `src/__init__.py` 및 각 서브모듈 패키지 초기화 파일 생성
    - _Requirements: 15.1, 15.3_
  
  - [x] 1.2 의존성 및 프로젝트 설정 파일 생성
    - `pyproject.toml` 생성 (pandas, networkx, openpyxl, pyarrow, streamlit, plotly, apscheduler, pytest, hypothesis)
    - `requirements.txt` 생성
    - _Requirements: 17.1_
  
  - [x] 1.3 Config Loader 유틸리티 구현
    - `src/utils/config_loader.py` 생성
    - YAML 파일 로드 및 dataclass 변환 함수 구현
    - CollectorConfig, PreprocessingConfig, NetworkConfig, AnalysisConfig 정의
    - _Requirements: 15.3, 15.4_
  
  - [x] 1.4 Logger 유틸리티 구현
    - `src/utils/logger.py` 생성
    - 구조화된 JSON 로깅 포맷 구현
    - _Requirements: 1.5, 1.7_
  
  - [x] 1.5 설정 YAML 파일 생성
    - `config/collector.yaml` 생성 (FTP 경로 템플릿, 대상 TSG+WG 목록, 재시도 설정 — 2026-09 노트북 재검증 결과 반영된 실제 경로 패턴 사용)
    - `config/preprocessing.yaml` 생성 (title_exclude_patterns, source_cleaning, membership_normalization, wi_delimiters, wi_exclude_patterns, date_range)
    - `config/network.yaml` 생성 (thresholds, time_units, tsg_groups)
    - `config/analysis.yaml` 생성 (louvain_seed, eigenvector_max_iter, random_network_samples)
    - `config/pipeline.yaml` 생성 (schedule 설정)
    - _Requirements: 1.3, 3.2, 4.2, 4.3, 5.2, 5.3, 6.2, 8.4, 9.4, 11.4, 14.1_
  
  - [x] 1.6 Config Loader 단위 테스트 작성
    - `tests/test_config.py` 생성
    - YAML 로드 및 dataclass 변환 검증
    - _Requirements: 17.1, 17.2_

- [x] 2. Checkpoint - 프로젝트 구조 검증
  - 모든 설정 파일이 로드되는지 확인
  - 테스트 실행하여 기본 구조 검증
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. FTP Collector 모듈 구현 (Stage 1)
  - [x] 3.1 FTPCollector 클래스 구현
    - `src/collector/__init__.py` 및 `src/collector/ftp_collector.py` 생성
    - TDocFileInfo, DownloadResult, CollectionReport dataclass 정의
    - discover_files(): FTP 서버 탐색 및 파일 목록 반환. `ftp_base_path_template`(`/tsg_{tsg_lower}/TSG_{tsg}/TSGR_{mtg}/Docs/`)로 TSG 총회 및 `targets`에 설정된 WG(WG1~WG6) 디렉토리를 모두 순회
    - download_file(): 단일 파일 다운로드 (재시도 로직 포함, 원본 노트북에 없던 신규 안정성 로직)
    - collect_all(): 전체 수집 프로세스 실행
    - 로컬 파일 존재 시 스킵 로직 구현
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 1.7_
  
  - [x] 3.2 FTPCollector 단위 테스트 작성
    - `tests/test_collector.py` 생성
    - 파일명 패턴 파싱 테스트 (Property 1)
    - 로컬 파일 존재 시 스킵 테스트 (Property 2)
    - Mock FTP 서버를 사용한 다운로드 테스트
    - _Requirements: 17.1, 17.2_

- [x] 4. Parser 모듈 구현 (Stage 1.5)
  - [x] 4.1 TDocParser 클래스 구현
    - `src/parser/__init__.py` 및 `src/parser/xlsx_parser.py` 생성
    - parse_file(): 단일 xlsx 파일 파싱
    - parse_all(): 모든 파일 병합
    - extract_release(): Release 문자열에서 정수 추출
    - 필수 컬럼 검증 및 누락 시 경고 로그
    - 파일명에서 TSG, WG, MTG 메타데이터 추출
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  
  - [x] 4.2 Parquet 직렬화 함수 구현
    - DataFrame을 Parquet으로 저장/로드하는 유틸리티 함수
    - `data/interim/parsed_tdocs.parquet` 경로로 저장
    - 이 유틸리티는 Preprocessor(Stage 2-5) 결과를 `data/interim/`에 저장할 때도 재사용한다 (요구사항 7.1)
    - _Requirements: 2.6, 7.1_
  
  - [x] 4.3 Parser 단위 테스트 작성
    - `tests/test_parser.py` 생성
    - DataFrame 스키마 일관성 테스트 (Property 3)
    - Release 파싱 정확성 테스트 (Property 4)
    - Parquet round-trip 테스트 (Property 5)
    - _Requirements: 17.1, 17.2, 17.3_

- [x] 5. Checkpoint - 데이터 수집 및 파싱 검증
  - Collector와 Parser 통합 테스트
  - 샘플 데이터로 파싱 결과 확인
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Title Filter 구현 (Stage 2)
  - [x] 6.1 TitleFilter 클래스 구현
    - `src/preprocessor/__init__.py` 및 `src/preprocessor/title_filter.py` 생성
    - FilterStats dataclass 정의
    - filter(): Title 패턴 매칭 및 필터링 (case-insensitive)
    - 12개 LS 패턴 + CR pack 패턴 적용 (2026-09 원본 노트북 재검증 결과 정정, 이전 "13개"는 오기)
    - 제외 통계 로깅
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  
  - [x] 6.2 TitleFilter 단위 테스트 작성
    - `tests/test_preprocessor.py` 생성
    - 패턴 기반 필터링 case-insensitive 테스트 (Property 6)
    - _Requirements: 17.1, 17.2_

- [x] 7. Source 정제 및 멤버십 기반 추출 구현 (Stage 3)
  - [x] 7.1 SourceCleaner 클래스 구현
    - `src/preprocessor/membership_extractor.py` 생성
    - SourceCleaningConfig dataclass 정의
    - clean(): Source 문자열 정제 (4단계)
      - CMCC → China Mobile 치환
      - 대괄호 제거
      - 마침표 제거
      - 단어 경계 공백 추가
    - clean_batch(): 일괄 정제
    - _Requirements: 4.2_
  
  - [x] 7.2 SourceCleaner Property 테스트 작성
    - Source 정제 멱등성 테스트 (Property 8)
    - CMCC 예외처리 정확성 테스트 (Property 10)
    - _Requirements: 17.1_
  
  - [x] 7.3 MembershipNormalizer 클래스 구현
    - NormalizationConfig dataclass 및 NormalizationStep dataclass 정의
    - 8단계 정규화 메서드 구현:
      - _remove_stopwords(): 법인격(47개) + 일반 단어(15개) 총 62개 제거 (2026-09 노트북 재검증 결과 정정)
      - _remove_countries(): 국가명 suffix 23개 제거 (2026-09 노트북 재검증 결과 정정)
      - _remove_specific(): 지명 4개 제거
      - _apply_replaces(): 특수 매핑 15개 적용 (2026-09 노트북 재검증 결과 정정)
      - _remove_brackets(): 괄호 및 내용 제거
      - _merge_startswith(): prefix 기반 통합 (예외 4개)
      - _remove_suffix(): 접미어 54개 제거
      - _remove_prefix(): 접두어 8개 제거
    - normalize(): 8단계 순차 적용
    - normalize_with_trace(): 단계별 추적 정보 포함
    - build_lookup_table(): 멤버십 검색 테이블 구축
    - get_stage_statistics(): 단계별 고유 기업 수 통계
    - _Requirements: 4.3_
  
  - [x] 7.4 MembershipNormalizer Property 테스트 작성
    - 정규화 순서 의존성 테스트 (Property 9)
    - 정규화 단계별 기업 수 단조 감소 테스트 (Property 11)
    - _Requirements: 17.1_
  
  - [x] 7.5 MembershipExtractor 클래스 구현
    - ExtractionStats dataclass 정의
    - _build_lookup_table(): 멤버십 + 수작업 alias 검색 테이블 구축
    - extract_companies(): Source에서 기업명 리스트 추출
    - process(): 전체 DataFrame 처리 (추출 + explode)
    - get_unmatched_sources(): 미매칭 Source 기록
    - _compute_source_hash() + CacheManager 연동: 입력 Source 목록 해시 기반 매핑 결과 캐싱 (요구사항 4.9, 요구사항 7.2의 파일 mtime 캐시와 별개 키 전략)
    - _Requirements: 4.1, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_
  
  - [x] 7.6 MembershipExtractor Property 테스트 작성
    - 멤버십 기반 기업 추출 정확성 테스트 (Property 7)
    - _Requirements: 17.1_

- [x] 8. WI Exploder 및 Temporal Enricher 구현 (Stage 4-5)
  - [x] 8.1 WIExploder 클래스 구현
    - `src/preprocessor/wi_exploder.py` 생성
    - ExplodeStats dataclass 정의
    - explode(): Work Item 분리 및 TEI/DUMMY 필터링
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [x] 8.2 TemporalEnricher 클래스 구현
    - `src/preprocessor/temporal_enricher.py` 생성
    - EnrichStats dataclass 정의
    - enrich(): Year, Quarter 컬럼 생성 및 날짜 범위 필터링
    - Stage 2~5 전 단계의 FilterStats/ExtractionStats/ExplodeStats/EnrichStats를 통합하여 단계별 적용 규칙과 영향도(제거/변환 레코드 수)를 메타데이터로 기록 (요구사항 7.3)
    - _Requirements: 6.1, 6.2, 6.3, 7.3_
  
  - [x] 8.3 WI/Temporal Property 테스트 작성
    - Explode 후 행 수 정확성 테스트 (Property 12)
    - 날짜 변환 및 범위 필터링 정확성 테스트 (Property 13)
    - _Requirements: 17.1_

- [x] 9. Cache Manager 구현
  - [x] 9.1 CacheManager 클래스 구현
    - `src/utils/cache_manager.py` 생성
    - get_cache_key(): 입력 파일 수정 시각 기반 캐시 키 생성
    - is_valid(): 캐시 유효성 검증
    - load(): 캐시된 결과 로드
    - save(): 결과를 캐시에 저장
    - _Requirements: 7.2_
  
  - [x] 9.2 CacheManager Property 테스트 작성
    - 캐시 무효화 정확성 테스트 (Property 14)
    - _Requirements: 17.1_

- [x] 10. Checkpoint - 전처리 파이프라인 검증
  - Title Filter → Membership Extraction → WI Explode → Temporal Enrich 통합 테스트
  - 전처리 결과 Parquet 저장 확인
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Network Builder 모듈 구현 (Stage 6)
  - [x] 11.1 CompanyNetworkBuilder 클래스 구현
    - `src/network/__init__.py` 및 `src/network/company_network.py` 생성
    - CompanyEdgeSchema dataclass 정의
    - build_edges(): 기업 간 Edge list 생성 (itertools.combinations)
    - Edge 정규화 (Source < Target)
    - Weight = 공동 기고 WI 수
    - threshold 적용
    - build_all(): TSG × 시간 단위 × threshold 전체 조합 생성
    - Parquet 형식으로 `data/processed/` 저장
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
  
  - [x] 11.2 WINetworkBuilder 클래스 구현
    - `src/network/wi_network.py` 생성
    - WIEdgeSchema dataclass 정의
    - build_edges(): WI 간 Edge list 생성
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  
  - [x] 11.3 Network Builder Property 테스트 작성
    - `tests/test_network.py` 생성
    - Edge 생성 정확도 테스트 (Property 15)
    - nC2 Edge 수 검증
    - Edge 정규화 검증 (Source < Target)
    - threshold 필터링 검증
    - _Requirements: 17.1_

- [x] 12. Network Analyzer 모듈 구현 (Stage 7)
  - [x] 12.1 NetworkStatistics 클래스 구현
    - `src/analyzer/__init__.py` 및 `src/analyzer/statistics.py` 생성
    - NetworkStats dataclass 정의
    - compute(): nodes, edges, density, diameter, avg_path_length 등 계산 (modularity는 CommunityDetector.detect() 결과를 재사용 — 12.5와 실행 순서 조정, Louvain 중복 실행 방지)
    - LCC 기준 diameter/avg_path_length 계산, LCC 노드 수 2개 미만 시 null 처리 (원본 노트북에 없던 신규 방어 로직)
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  
  - [x] 12.2 NetworkStatistics Property 테스트 작성
    - `tests/test_analyzer.py` 생성
    - 네트워크 통계 계산 정확성 테스트 (Property 16)
    - _Requirements: 17.1_
  
  - [x] 12.3 CentralityAnalyzer 클래스 구현
    - `src/analyzer/centrality.py` 생성
    - compute_all(): Degree, Betweenness, Closeness, Eigenvector Centrality 계산 (비가중/unweighted — 요구사항 11.1 참고)
    - 0~1 정규화
    - Eigenvector max_iter=1000 설정, 미수렴 시(PowerIterationFailedConvergence) null 처리 및 경고 로그
    - _Requirements: 11.1, 11.2, 11.3_
  
  - [x] 12.4 CentralityAnalyzer Property 테스트 작성
    - 중심성 정규화 테스트 (Property 17)
    - _Requirements: 17.1_
  
  - [x] 12.5 CommunityDetector 클래스 구현
    - `src/analyzer/community.py` 생성
    - CommunityResult dataclass 정의
    - detect(): python-louvain(`community_louvain.best_partition(G, random_state=42)`)로 커뮤니티 탐지, seed 고정은 요구사항 16.2 재현성을 위한 신규 설계 결정(원본 노트북은 randomize=True로 비결정적이었음)
    - 노드별 커뮤니티 ID 및 커뮤니티별 노드 목록 반환, modularity는 NetworkStatistics(12.1)가 재사용하도록 반환값에 포함 (Louvain 중복 실행 방지)
    - 중심성(12.3) 및 커뮤니티 분석 결과를 Parquet 형식으로 저장
    - _Requirements: 11.4, 11.5, 11.6_
  
  - [x] 12.6 AdvancedAnalyzer 클래스 구현
    - `src/analyzer/advanced.py` 생성
    - 적용 범위: TSG × 연도 × threshold=0 조합에 한정 실행 (요구사항 12 "적용 범위" 참고, 전체 조합 실행 시 성능 예산 초과 위험)
    - analyze_power_law(): Power-law 적합성 검증, exponent + p-value(`powerlaw.Fit.distribution_compare`) 계산 (원본 노트북은 exponent만 계산했으므로 p-value는 신규 구현)
    - compute_small_world(): Erdős–Rényi 무작위 네트워크 `random_network_samples`개 생성 후 σ=(C/C_rand)/(L/L_rand) 실제 계산 (원본 노트북에 없던 전적으로 신규 구현, nx.sigma() 직접 사용 금지 — 성능 이슈)
    - extract_mst(): Maximum Spanning Tree 추출
    - analyze_centrality_correlation(): TSG별 Degree Centrality **순위**에 대한 Spearman 상관계수 (원본 노트북은 원본 값에 Pearson을 적용한 오류가 있었으므로 재현하지 않음)
    - sensitivity_analysis(): 대표 시간 값에서 threshold 0~9 민감도 분석
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_
  
  - [x] 12.7 AdvancedAnalyzer Property 테스트 작성
    - Maximum Spanning Tree 속성 테스트 (Property 18)
    - _Requirements: 17.1_

- [x] 13. Checkpoint - 네트워크 분석 검증
  - Network Builder + Analyzer 통합 테스트
  - 샘플 데이터로 분석 결과 확인
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Dashboard 모듈 구현 (Stage 8)
  - [x] 14.1 Dashboard 데이터 로더 구현
    - `src/dashboard/__init__.py` 및 `src/dashboard/app.py` 생성
    - 분석 결과 데이터 로드 함수
    - _Requirements: 13.1_
  
  - [x] 14.2 사이드바 필터 패널 구현
    - TSG 그룹, 시간 단위, 시간 범위, threshold, 네트워크 유형 선택
    - _Requirements: 13.1_
  
  - [x] 14.3 네트워크 그래프 시각화 구현
    - `src/dashboard/components/` 디렉토리 생성
    - Plotly 네트워크 그래프 (노드 크기=Degree, 색상=커뮤니티, Edge 굵기=Weight)
    - 사전 계산된 분석 결과(Parquet)를 로드하는 방식으로 5초 이내 로딩 보장 (요구사항 16.3, 그래프를 매 요청마다 재계산하지 않음)
    - _Requirements: 13.2, 16.3_
  
  - [x] 14.4 통계 차트 및 테이블 구현
    - 시계열 통계 라인 차트
    - Centrality 순위 테이블 (검색 기능 포함)
    - 커뮤니티 목록 뷰
    - _Requirements: 13.3, 13.4, 13.5_
  
  - [x] 14.5 에러 처리 및 빈 데이터 처리
    - 데이터 없음 메시지 표시
    - _Requirements: 13.6_

- [x] 15. Pipeline Scheduler 구현
  - [x] 15.1 PipelineScheduler 클래스 구현
    - `src/scheduler/__init__.py` 및 `src/scheduler/pipeline_scheduler.py` 생성
    - APScheduler 기반 자동 스케줄링
    - start(), stop(), run_pipeline() 메서드
    - 예외 발생 시 로깅 및 다음 실행 유지
    - _Requirements: 14.1, 14.2, 14.3, 14.4_
  
  - [x] 15.2 독립 모듈 실행 엔트리포인트 구현
    - 각 모듈에 `__main__.py` 추가
    - `python -m src.collector` 형식 실행 지원
    - _Requirements: 15.2_

- [x] 16. 파이프라인 통합 및 재현성 테스트
  - [x] 16.1 전체 파이프라인 통합 테스트 구현
    - `tests/test_integration.py` 생성
    - Collector → Parser → Preprocessor → Network Builder → Analyzer 전체 흐름 테스트
    - 수집을 제외한 전처리~분석 전 단계가 30분 이내에 완료되는지 시간 측정 테스트 포함 (대표 데이터셋 기준, 요구사항 16.1)
    - _Requirements: 16.1, 17.1_
  
  - [x] 16.2 파이프라인 재현성 Property 테스트 작성
    - 동일 입력에 대한 결과 동등성 테스트 (Property 19)
    - random_seed 고정 검증
    - _Requirements: 16.2, 17.1_

- [x] 17. Final Checkpoint - 전체 시스템 검증
  - 모든 단위 테스트 통과 확인
  - 통합 테스트 실행
  - 성능 벤치마크 실행: 전처리~분석 30분 이내(요구사항 16.1), 대시보드 그래프 로딩 5초 이내(요구사항 16.3) 확인
  - Dashboard 로컬 실행 테스트 (`streamlit run src/dashboard/app.py`, 요구사항 13.7)
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (19개)
- Unit tests validate specific examples and edge cases
- 기존 `raw/` 폴더의 Jupyter Notebook은 참조 전용으로 보존하며 수정하지 않음
- 모든 설정값은 `config/` 디렉토리의 YAML 파일에서 관리

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4"] },
    { "id": 2, "tasks": ["1.5", "1.6"] },
    { "id": 3, "tasks": ["3.1", "4.1"] },
    { "id": 4, "tasks": ["3.2", "4.2"] },
    { "id": 5, "tasks": ["4.3", "6.1"] },
    { "id": 6, "tasks": ["6.2", "7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3"] },
    { "id": 8, "tasks": ["7.4", "7.5"] },
    { "id": 9, "tasks": ["7.6", "8.1"] },
    { "id": 10, "tasks": ["8.2", "8.3"] },
    { "id": 11, "tasks": ["9.1", "9.2"] },
    { "id": 12, "tasks": ["11.1"] },
    { "id": 13, "tasks": ["11.2", "11.3"] },
    { "id": 14, "tasks": ["12.1"] },
    { "id": 15, "tasks": ["12.2", "12.3"] },
    { "id": 16, "tasks": ["12.4", "12.5"] },
    { "id": 17, "tasks": ["12.6", "12.7"] },
    { "id": 18, "tasks": ["14.1", "14.2"] },
    { "id": 19, "tasks": ["14.3", "14.4"] },
    { "id": 20, "tasks": ["14.5", "15.1"] },
    { "id": 21, "tasks": ["15.2", "16.1"] },
    { "id": 22, "tasks": ["16.2"] }
  ]
}
```
