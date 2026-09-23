"""
TDoc Parser Module (Stage 1.5)

TDoc List xlsx 파일을 표준화된 DataFrame으로 파싱하는 모듈.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from src.utils.config_loader import PreprocessingConfig
from src.utils.logger import get_logger

# 로거 초기화
logger = get_logger("parser", default_stage="parse")


@dataclass
class ParseStats:
    """파싱 통계 데이터.
    
    Attributes:
        total_files: 총 파일 수
        successful_files: 성공적으로 파싱된 파일 수
        failed_files: 파싱 실패한 파일 수
        skipped_files: 건너뛴 파일 수 (패턴 불일치 등)
        total_rows: 전체 파싱된 행 수
        files_with_missing_columns: 필수 컬럼 누락 파일 목록
        files_with_pattern_mismatch: 패턴 불일치 파일 목록
    """
    total_files: int = 0
    successful_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    total_rows: int = 0
    files_with_missing_columns: List[Dict[str, Any]] = field(default_factory=list)
    files_with_pattern_mismatch: List[str] = field(default_factory=list)


class TDocParser:
    """TDoc List xlsx 파일을 표준화된 DataFrame으로 파싱.
    
    3GPP FTP 서버에서 수집한 TDoc List xlsx 파일을 파싱하여
    표준화된 컬럼 구조의 DataFrame으로 변환한다.
    
    파일명 패턴: TDoc_List_Meeting_{TSG}#{MTG_NUM}.xlsx
        - 예: TDoc_List_Meeting_RAN#100.xlsx
        - e-meeting 접미사: TDoc_List_Meeting_RAN#100-e.xlsx
    
    Requirements:
        - 2.1: TDoc, Title, Source, Related WIs, Release, Uploaded 컬럼 파싱
        - 2.2: Release 컬럼에서 정수 릴리즈 번호 추출
        - 2.3: 파일명에서 TSG, WG, MTG 정보 추출
        - 2.4: 필수 컬럼 누락 시 경고 로그 및 파일 건너뛰기
        - 2.5: 파일명 패턴 불일치 시 경고 로그 및 파일 건너뛰기
        - 2.6: Parquet round-trip 동등성 보장
    
    Attributes:
        REQUIRED_COLUMNS: 필수 컬럼 목록 (TDoc, Title, Source)
        OUTPUT_COLUMNS: 출력 DataFrame 컬럼 목록
    """
    
    # 필수 컬럼 - 누락 시 파일 건너뛰기
    REQUIRED_COLUMNS = ['TDoc', 'Title', 'Source']
    
    # 출력 컬럼 - Type 컬럼은 원본 데이터에 근거가 없어 제외
    OUTPUT_COLUMNS = [
        'TDoc', 'Title', 'Source', 'Related WIs',
        'Release', 'Uploaded', 'TSG', 'WG', 'MTG'
    ]
    
    # 파일명 패턴: TDoc_List_Meeting_{TSG}#{MTG_NUM}.xlsx
    # e-meeting 접미사 허용: #{MTG_NUM}-e.xlsx
    # TSG 또는 WG 모두 매칭: RAN, SA, CT, RAN1, SA2, CT4 등
    FILENAME_PATTERN = re.compile(
        r'TDoc_List_Meeting_([A-Z]+\d*)#(\d+)(?:-e)?\.xlsx$',
        re.IGNORECASE
    )
    
    # 디렉토리 경로에서 TSG 추출 패턴
    TSG_DIR_PATTERN = re.compile(r'^(RAN|SA|CT)$', re.IGNORECASE)
    
    def __init__(self, config: Optional[PreprocessingConfig] = None):
        """TDocParser 초기화.
        
        Args:
            config: 전처리 설정 객체. None이면 기본 설정 사용.
        """
        self.config = config
        self._stats = ParseStats()
    
    def parse_file(self, file_path: Union[str, Path]) -> Optional[pd.DataFrame]:
        """단일 xlsx 파일을 파싱.
        
        파일명에서 TSG, WG, MTG 메타데이터를 추출하고,
        xlsx 파일의 내용을 DataFrame으로 변환한다.
        
        Args:
            file_path: xlsx 파일 경로
            
        Returns:
            표준화된 DataFrame 또는 None (파싱 실패 시)
            
        Note:
            - 필수 컬럼(TDoc, Title, Source) 누락 시 None 반환 및 경고 로그
            - 파일명 패턴 불일치 시 None 반환 및 경고 로그
        """
        file_path = Path(file_path)
        
        # 파일 존재 확인
        if not file_path.exists():
            logger.warning_with_details(
                f"파일이 존재하지 않습니다: {file_path}",
                stage="parse",
                details={"file": str(file_path), "reason": "file_not_found"}
            )
            return None
        
        # 파일명 패턴 검증 및 메타데이터 추출 (요구사항 2.5)
        metadata = self._extract_metadata_from_path(file_path)
        if metadata is None:
            self._stats.skipped_files += 1
            self._stats.files_with_pattern_mismatch.append(str(file_path))
            logger.warning_with_details(
                f"파일명 패턴 불일치로 건너뜁니다: {file_path.name}",
                stage="parse",
                details={
                    "file": str(file_path),
                    "filename": file_path.name,
                    "reason": "pattern_mismatch",
                    "expected_pattern": "TDoc_List_Meeting_{TSG/WG}#{MTG}.xlsx"
                }
            )
            return None
        
        try:
            # xlsx 파일 읽기
            df = pd.read_excel(file_path, engine='openpyxl')
            
            # 필수 컬럼 검증 (요구사항 2.4)
            missing_columns = self._check_required_columns(df)
            if missing_columns:
                self._stats.failed_files += 1
                self._stats.files_with_missing_columns.append({
                    "file": str(file_path),
                    "missing_columns": missing_columns
                })
                logger.warning_with_details(
                    f"필수 컬럼 누락으로 파일을 건너뜁니다: {file_path.name}",
                    stage="parse",
                    details={
                        "file": str(file_path),
                        "missing_columns": missing_columns,
                        "reason": "missing_required_columns"
                    }
                )
                return None
            
            # 컬럼 정규화 (대소문자, 공백 정리)
            df = self._normalize_columns(df)
            
            # Release 컬럼 정수 추출 (요구사항 2.2)
            if 'Release' in df.columns:
                df['Release'] = df['Release'].apply(self.extract_release)
            else:
                df['Release'] = None
            
            # 메타데이터 컬럼 추가 (요구사항 2.3)
            df['TSG'] = metadata['tsg']
            df['WG'] = metadata['wg']
            df['MTG'] = metadata['mtg']
            
            # 출력 컬럼만 선택 및 순서 정렬
            df = self._select_output_columns(df)
            
            self._stats.successful_files += 1
            self._stats.total_rows += len(df)
            
            logger.debug_with_details(
                f"파일 파싱 성공: {file_path.name}",
                stage="parse",
                details={
                    "file": str(file_path),
                    "rows": len(df),
                    "tsg": metadata['tsg'],
                    "wg": metadata['wg'],
                    "mtg": metadata['mtg']
                }
            )
            
            return df
            
        except Exception as e:
            self._stats.failed_files += 1
            logger.error_with_details(
                f"파일 파싱 중 오류 발생: {file_path.name}",
                stage="parse",
                details={
                    "file": str(file_path),
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None
    
    def parse_all(self, raw_dir: Union[str, Path]) -> pd.DataFrame:
        """모든 xlsx 파일을 파싱하여 병합.
        
        raw_dir 디렉토리 하위의 모든 TDoc List xlsx 파일을 파싱하고
        단일 DataFrame으로 병합한다.
        
        Args:
            raw_dir: 원본 xlsx 파일이 저장된 디렉토리 경로
                     (예: data/raw/ - 하위에 RAN/, SA/, CT/ 디렉토리 존재)
            
        Returns:
            모든 파일이 병합된 DataFrame (파일이 없으면 빈 DataFrame)
        """
        raw_dir = Path(raw_dir)
        
        if not raw_dir.exists():
            logger.warning_with_details(
                f"raw 디렉토리가 존재하지 않습니다: {raw_dir}",
                stage="parse",
                details={"directory": str(raw_dir)}
            )
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)
        
        # 통계 초기화
        self._stats = ParseStats()
        
        # 모든 xlsx 파일 탐색 (TDoc_List 패턴만)
        xlsx_files = list(raw_dir.rglob("TDoc_List*.xlsx"))
        self._stats.total_files = len(xlsx_files)
        
        if not xlsx_files:
            logger.info_with_details(
                "파싱할 TDoc List 파일이 없습니다",
                stage="parse",
                details={"directory": str(raw_dir)}
            )
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)
        
        logger.info_with_details(
            f"파싱 시작: {len(xlsx_files)}개 파일 발견",
            stage="parse",
            details={"directory": str(raw_dir), "file_count": len(xlsx_files)}
        )
        
        # 각 파일 파싱
        dfs: List[pd.DataFrame] = []
        for file_path in xlsx_files:
            df = self.parse_file(file_path)
            if df is not None and len(df) > 0:
                dfs.append(df)
        
        # 결과 병합
        if not dfs:
            logger.warning_with_details(
                "파싱된 데이터가 없습니다",
                stage="parse",
                details=self._get_stats_dict()
            )
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)
        
        result = pd.concat(dfs, ignore_index=True)
        
        logger.info_with_details(
            f"파싱 완료: {len(result)}행 생성",
            stage="parse",
            details=self._get_stats_dict()
        )
        
        return result
    
    def extract_release(self, release_str: Any) -> Optional[int]:
        r"""Release 문자열에서 정수 버전 추출.
        
        다양한 형식의 Release 표기에서 숫자를 추출한다.
        원본 노트북의 방식과 동일하게 str.extract(r'(\d+)')로 첫 숫자만 추출.
        
        Args:
            release_str: Release 문자열 (예: "Rel-15", "Release 16", "R17", "rel15")
            
        Returns:
            정수 릴리즈 번호 또는 None
            
        Examples:
            >>> parser.extract_release("Rel-15")
            15
            >>> parser.extract_release("Release 16")
            16
            >>> parser.extract_release("R17")
            17
            >>> parser.extract_release("rel15")
            15
            >>> parser.extract_release("")
            None
        """
        if release_str is None or pd.isna(release_str):
            return None
        
        # 문자열로 변환
        release_str = str(release_str).strip()
        
        if not release_str:
            return None
        
        # 첫 번째 숫자 추출 (원본 노트북 방식: str.extract(r'(\d+)'))
        match = re.search(r'(\d+)', release_str)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        
        return None
    
    def get_stats(self) -> ParseStats:
        """파싱 통계 반환.
        
        Returns:
            ParseStats 객체
        """
        return self._stats
    
    def _extract_metadata_from_path(
        self, file_path: Path
    ) -> Optional[Dict[str, Union[str, int]]]:
        """파일 경로에서 TSG, WG, MTG 메타데이터 추출.
        
        파일명과 디렉토리 경로를 분석하여 메타데이터를 추출한다.
        
        Args:
            file_path: xlsx 파일 경로
            
        Returns:
            메타데이터 딕셔너리 {'tsg': str, 'wg': str, 'mtg': int}
            또는 None (패턴 불일치 시)
        """
        # 파일명에서 패턴 매칭
        match = self.FILENAME_PATTERN.search(file_path.name)
        if not match:
            return None
        
        # 파일명에서 추출한 그룹명과 회차
        group_name = match.group(1).upper()  # RAN, SA, CT, RAN1, SA2 등
        mtg = int(match.group(2))
        
        # TSG와 WG 결정
        # 파일명이 "RAN", "SA", "CT"이면 TSG 총회
        # 파일명이 "RAN1", "SA2" 등이면 WG
        if group_name in ('RAN', 'SA', 'CT'):
            tsg = group_name
            wg = 'TSG'  # 총회
        else:
            # WG인 경우: RAN1 → TSG=RAN, WG=WG1
            # 숫자 분리
            tsg_match = re.match(r'^(RAN|SA|CT)(\d+)$', group_name)
            if tsg_match:
                tsg = tsg_match.group(1)
                wg_num = tsg_match.group(2)
                wg = f"WG{wg_num}"
            else:
                # 알 수 없는 형식 - 디렉토리에서 TSG 추정
                tsg = self._infer_tsg_from_directory(file_path)
                wg = group_name
        
        return {
            'tsg': tsg,
            'wg': wg,
            'mtg': mtg
        }
    
    def _infer_tsg_from_directory(self, file_path: Path) -> str:
        """디렉토리 경로에서 TSG 추론.
        
        파일이 위치한 디렉토리 경로에서 TSG 그룹을 추론한다.
        
        Args:
            file_path: 파일 경로
            
        Returns:
            TSG 이름 (RAN, SA, CT) 또는 "UNKNOWN"
        """
        # 경로의 각 부분에서 TSG 찾기
        for part in file_path.parts:
            if self.TSG_DIR_PATTERN.match(part):
                return part.upper()
        
        return "UNKNOWN"
    
    def _check_required_columns(self, df: pd.DataFrame) -> List[str]:
        """필수 컬럼 존재 여부 확인.
        
        Args:
            df: 검사할 DataFrame
            
        Returns:
            누락된 컬럼 목록 (모두 존재하면 빈 리스트)
        """
        # 대소문자 무시하여 컬럼 매칭
        existing_cols_lower = {col.lower(): col for col in df.columns}
        
        missing = []
        for req_col in self.REQUIRED_COLUMNS:
            if req_col.lower() not in existing_cols_lower:
                missing.append(req_col)
        
        return missing
    
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """컬럼명 정규화.
        
        대소문자와 공백을 정리하여 표준 컬럼명으로 매핑한다.
        
        Args:
            df: 원본 DataFrame
            
        Returns:
            정규화된 컬럼명을 가진 DataFrame
        """
        # 컬럼명 매핑 (원본 → 표준)
        column_mapping = {}
        
        # 대소문자 무시 매핑
        standard_cols = {
            'tdoc': 'TDoc',
            'title': 'Title',
            'source': 'Source',
            'related wis': 'Related WIs',
            'related wi': 'Related WIs',
            'related_wis': 'Related WIs',
            'release': 'Release',
            'uploaded': 'Uploaded',
            'upload date': 'Uploaded',
        }
        
        for col in df.columns:
            col_lower = col.lower().strip()
            if col_lower in standard_cols:
                column_mapping[col] = standard_cols[col_lower]
        
        return df.rename(columns=column_mapping)
    
    def _select_output_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """출력 컬럼 선택 및 순서 정렬.
        
        OUTPUT_COLUMNS에 정의된 컬럼만 선택하고 순서를 맞춘다.
        존재하지 않는 컬럼은 None으로 채운다.
        
        Args:
            df: 파싱된 DataFrame
            
        Returns:
            표준 컬럼 구조의 DataFrame
        """
        result = pd.DataFrame()
        
        for col in self.OUTPUT_COLUMNS:
            if col in df.columns:
                result[col] = df[col]
            else:
                result[col] = None
        
        return result
    
    def _get_stats_dict(self) -> Dict[str, Any]:
        """통계를 딕셔너리로 변환.
        
        Returns:
            통계 딕셔너리
        """
        return {
            "total_files": self._stats.total_files,
            "successful_files": self._stats.successful_files,
            "failed_files": self._stats.failed_files,
            "skipped_files": self._stats.skipped_files,
            "total_rows": self._stats.total_rows,
            "files_with_missing_columns": len(self._stats.files_with_missing_columns),
            "files_with_pattern_mismatch": len(self._stats.files_with_pattern_mismatch)
        }


def save_parsed_tdocs(
    df: pd.DataFrame,
    output_path: Union[str, Path],
    compression: str = "snappy"
) -> None:
    """파싱된 DataFrame을 Parquet 형식으로 저장.
    
    요구사항 2.6의 round-trip 동등성을 보장하기 위해
    Parquet 형식으로 저장한다.
    
    Note:
        이 함수는 하위 호환성을 위해 유지됩니다.
        새 코드에서는 src.utils.parquet_utils.save_to_parquet()를 사용하세요.
    
    Args:
        df: 저장할 DataFrame
        output_path: 출력 파일 경로 (예: data/interim/parsed_tdocs.parquet)
        compression: 압축 방식 (기본값: snappy)
    """
    from src.utils.parquet_utils import save_to_parquet
    
    save_to_parquet(df, output_path, compression=compression, metadata={"stage": "parser"})


def load_parsed_tdocs(input_path: Union[str, Path]) -> pd.DataFrame:
    """Parquet 파일에서 DataFrame 로드.
    
    Note:
        이 함수는 하위 호환성을 위해 유지됩니다.
        새 코드에서는 src.utils.parquet_utils.load_from_parquet()를 사용하세요.
    
    Args:
        input_path: Parquet 파일 경로
        
    Returns:
        로드된 DataFrame
    """
    from src.utils.parquet_utils import load_from_parquet
    
    return load_from_parquet(input_path)
