"""
Parquet 직렬화 유틸리티 모듈.

DataFrame을 Parquet 형식으로 저장/로드하는 범용 유틸리티 함수를 제공한다.
Parser(Stage 1.5)와 Preprocessor(Stage 2-5) 모두에서 재사용한다.

Requirements: 2.6, 7.1
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from src.utils.logger import get_logger

# 로거 초기화
logger = get_logger("parquet_utils", default_stage="io")

# 기본 경로 상수
DEFAULT_INTERIM_DIR = Path("data/interim")
DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_RESULTS_DIR = Path("data/results")

# 기본 Parquet 설정
DEFAULT_COMPRESSION = "snappy"
DEFAULT_ENGINE = "pyarrow"


def save_to_parquet(
    df: pd.DataFrame,
    output_path: Union[str, Path],
    compression: str = DEFAULT_COMPRESSION,
    index: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    """DataFrame을 Parquet 형식으로 저장.
    
    요구사항 2.6의 round-trip 동등성과 요구사항 7.1의 중간 결과 저장을 지원한다.
    
    Args:
        df: 저장할 DataFrame
        output_path: 출력 파일 경로 (예: data/interim/parsed_tdocs.parquet)
        compression: 압축 방식 (기본값: snappy). 
                    지원 방식: snappy, gzip, brotli, lz4, zstd, None
        index: DataFrame 인덱스 저장 여부 (기본값: False)
        metadata: Parquet 파일에 저장할 사용자 정의 메타데이터 (optional)
        
    Returns:
        저장된 파일의 Path 객체
        
    Raises:
        ValueError: DataFrame이 비어있는 경우
        IOError: 파일 저장 실패 시
        
    Examples:
        >>> df = pd.DataFrame({'A': [1, 2], 'B': ['x', 'y']})
        >>> save_to_parquet(df, 'data/interim/test.parquet')
        PosixPath('data/interim/test.parquet')
        
        >>> # 메타데이터와 함께 저장
        >>> save_to_parquet(
        ...     df, 
        ...     'data/interim/processed.parquet',
        ...     metadata={'stage': 'preprocessing', 'version': '1.0'}
        ... )
    """
    output_path = Path(output_path)
    
    # 부모 디렉토리 생성
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # pyarrow 테이블 생성 (메타데이터 추가를 위해)
        if metadata:
            import pyarrow as pa
            import pyarrow.parquet as pq
            
            table = pa.Table.from_pandas(df, preserve_index=index)
            
            # 기존 메타데이터와 사용자 메타데이터 병합
            existing_metadata = table.schema.metadata or {}
            combined_metadata = {
                **existing_metadata,
                **{k.encode(): str(v).encode() for k, v in metadata.items()}
            }
            table = table.replace_schema_metadata(combined_metadata)
            
            pq.write_table(
                table,
                output_path,
                compression=compression
            )
        else:
            # 간단한 저장
            df.to_parquet(
                output_path,
                engine=DEFAULT_ENGINE,
                compression=compression,
                index=index
            )
        
        logger.info_with_details(
            f"Parquet 파일 저장 완료: {output_path}",
            stage="save",
            details={
                "path": str(output_path),
                "rows": len(df),
                "columns": len(df.columns),
                "compression": compression,
                "has_metadata": metadata is not None
            }
        )
        
        return output_path
        
    except Exception as e:
        logger.error_with_details(
            f"Parquet 파일 저장 실패: {output_path}",
            stage="save",
            details={
                "path": str(output_path),
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
        )
        raise IOError(f"Parquet 파일 저장 실패: {e}") from e


def load_from_parquet(
    input_path: Union[str, Path],
    columns: Optional[List[str]] = None,
    filters: Optional[List[tuple]] = None,
) -> pd.DataFrame:
    """Parquet 파일에서 DataFrame 로드.
    
    요구사항 2.6의 round-trip 동등성을 보장한다.
    
    Args:
        input_path: Parquet 파일 경로
        columns: 로드할 컬럼 목록 (None이면 모든 컬럼 로드)
        filters: 필터 조건 리스트 (pyarrow 필터 형식)
                예: [('year', '>=', 2020)]
        
    Returns:
        로드된 DataFrame
        
    Raises:
        FileNotFoundError: 파일이 존재하지 않는 경우
        IOError: 파일 로드 실패 시
        
    Examples:
        >>> df = load_from_parquet('data/interim/parsed_tdocs.parquet')
        
        >>> # 특정 컬럼만 로드
        >>> df = load_from_parquet(
        ...     'data/interim/processed.parquet', 
        ...     columns=['TDoc', 'Source', 'company']
        ... )
        
        >>> # 필터와 함께 로드
        >>> df = load_from_parquet(
        ...     'data/interim/enriched.parquet',
        ...     filters=[('Year', '>=', 2020)]
        ... )
    """
    input_path = Path(input_path)
    
    if not input_path.exists():
        raise FileNotFoundError(f"파일이 존재하지 않습니다: {input_path}")
    
    try:
        df = pd.read_parquet(
            input_path,
            engine=DEFAULT_ENGINE,
            columns=columns,
            filters=filters
        )
        
        logger.info_with_details(
            f"Parquet 파일 로드 완료: {input_path}",
            stage="load",
            details={
                "path": str(input_path),
                "rows": len(df),
                "columns": len(df.columns),
                "selected_columns": columns,
                "has_filters": filters is not None
            }
        )
        
        return df
        
    except Exception as e:
        logger.error_with_details(
            f"Parquet 파일 로드 실패: {input_path}",
            stage="load",
            details={
                "path": str(input_path),
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
        )
        raise IOError(f"Parquet 파일 로드 실패: {e}") from e


def get_parquet_metadata(input_path: Union[str, Path]) -> Dict[str, Any]:
    """Parquet 파일의 메타데이터 조회.
    
    Args:
        input_path: Parquet 파일 경로
        
    Returns:
        메타데이터 딕셔너리 (스키마, 행 수, 사용자 메타데이터 등)
    """
    import pyarrow.parquet as pq
    
    input_path = Path(input_path)
    
    if not input_path.exists():
        raise FileNotFoundError(f"파일이 존재하지 않습니다: {input_path}")
    
    parquet_file = pq.ParquetFile(input_path)
    metadata = parquet_file.metadata
    schema = parquet_file.schema_arrow
    
    result = {
        "num_rows": metadata.num_rows,
        "num_columns": metadata.num_columns,
        "num_row_groups": metadata.num_row_groups,
        "created_by": metadata.created_by,
        "columns": [field.name for field in schema],
        "column_types": {field.name: str(field.type) for field in schema},
    }
    
    # 사용자 메타데이터 추출
    if schema.metadata:
        user_metadata = {}
        for key, value in schema.metadata.items():
            if not key.startswith(b'pandas'):  # pandas 내부 메타데이터 제외
                try:
                    user_metadata[key.decode()] = value.decode()
                except (UnicodeDecodeError, AttributeError):
                    pass
        if user_metadata:
            result["user_metadata"] = user_metadata
    
    return result


def verify_round_trip(df: pd.DataFrame, output_path: Union[str, Path]) -> bool:
    """Parquet round-trip 동등성 검증.
    
    요구사항 2.6: 직렬화 후 역직렬화한 결과가 원본과 동등해야 한다.
    
    Args:
        df: 원본 DataFrame
        output_path: 저장할 경로
        
    Returns:
        True if round-trip이 성공적으로 동등성을 유지, False otherwise
    """
    output_path = Path(output_path)
    
    # 저장
    save_to_parquet(df, output_path)
    
    # 로드
    loaded_df = load_from_parquet(output_path)
    
    # 동등성 검증
    try:
        pd.testing.assert_frame_equal(
            df.reset_index(drop=True), 
            loaded_df.reset_index(drop=True),
            check_dtype=True,
            check_exact=False,  # float 비교 시 tolerance 허용
            rtol=1e-5
        )
        
        logger.debug_with_details(
            f"Round-trip 검증 성공: {output_path}",
            stage="verify",
            details={"path": str(output_path), "rows": len(df)}
        )
        
        return True
        
    except AssertionError as e:
        logger.warning_with_details(
            f"Round-trip 검증 실패: {output_path}",
            stage="verify",
            details={
                "path": str(output_path),
                "error": str(e)
            }
        )
        return False


# 파이프라인별 특화 함수들

def save_parsed_tdocs(
    df: pd.DataFrame,
    output_dir: Union[str, Path] = DEFAULT_INTERIM_DIR,
    filename: str = "parsed_tdocs.parquet"
) -> Path:
    """파싱된 TDoc DataFrame 저장 (Stage 1.5).
    
    Args:
        df: 파싱된 DataFrame
        output_dir: 출력 디렉토리 (기본값: data/interim/)
        filename: 파일명 (기본값: parsed_tdocs.parquet)
        
    Returns:
        저장된 파일 경로
    """
    output_path = Path(output_dir) / filename
    return save_to_parquet(df, output_path, metadata={"stage": "parser"})


def load_parsed_tdocs(
    input_dir: Union[str, Path] = DEFAULT_INTERIM_DIR,
    filename: str = "parsed_tdocs.parquet"
) -> pd.DataFrame:
    """파싱된 TDoc DataFrame 로드.
    
    Args:
        input_dir: 입력 디렉토리 (기본값: data/interim/)
        filename: 파일명 (기본값: parsed_tdocs.parquet)
        
    Returns:
        로드된 DataFrame
    """
    input_path = Path(input_dir) / filename
    return load_from_parquet(input_path)


def save_preprocessed_data(
    df: pd.DataFrame,
    stage_name: str,
    output_dir: Union[str, Path] = DEFAULT_INTERIM_DIR,
) -> Path:
    """전처리 단계별 중간 결과 저장 (Stage 2-5).
    
    요구사항 7.1: 전처리 결과를 data/interim/에 저장한다.
    
    Args:
        df: 전처리된 DataFrame
        stage_name: 단계 이름 (예: 'title_filtered', 'membership_extracted', 
                    'wi_exploded', 'temporal_enriched')
        output_dir: 출력 디렉토리 (기본값: data/interim/)
        
    Returns:
        저장된 파일 경로
    """
    filename = f"{stage_name}.parquet"
    output_path = Path(output_dir) / filename
    return save_to_parquet(df, output_path, metadata={"stage": stage_name})


def load_preprocessed_data(
    stage_name: str,
    input_dir: Union[str, Path] = DEFAULT_INTERIM_DIR,
) -> pd.DataFrame:
    """전처리 단계별 중간 결과 로드.
    
    Args:
        stage_name: 단계 이름 (예: 'title_filtered', 'membership_extracted')
        input_dir: 입력 디렉토리 (기본값: data/interim/)
        
    Returns:
        로드된 DataFrame
    """
    filename = f"{stage_name}.parquet"
    input_path = Path(input_dir) / filename
    return load_from_parquet(input_path)


def save_network_edges(
    df: pd.DataFrame,
    network_type: str,
    tsg_group: str,
    time_unit: str,
    time_value: Union[int, str],
    threshold: int,
    output_dir: Union[str, Path] = DEFAULT_PROCESSED_DIR,
) -> Path:
    """네트워크 Edge list 저장 (Stage 6).
    
    Args:
        df: Edge list DataFrame
        network_type: 네트워크 유형 ('company' 또는 'wi')
        tsg_group: TSG 그룹 ('ALL', 'RAN', 'SA', 'CT')
        time_unit: 시간 단위 ('year', 'release', 'quarter')
        time_value: 시간 값
        threshold: Weight 임계값
        output_dir: 출력 디렉토리 (기본값: data/processed/)
        
    Returns:
        저장된 파일 경로
    """
    filename = f"{network_type}_edges_{tsg_group}_{time_unit}_{time_value}_th{threshold}.parquet"
    output_path = Path(output_dir) / filename
    
    metadata = {
        "network_type": network_type,
        "tsg_group": tsg_group,
        "time_unit": time_unit,
        "time_value": str(time_value),
        "threshold": str(threshold)
    }
    
    return save_to_parquet(df, output_path, metadata=metadata)


def save_analysis_results(
    df: pd.DataFrame,
    analysis_type: str,
    output_dir: Union[str, Path] = DEFAULT_RESULTS_DIR,
    filename: Optional[str] = None,
) -> Path:
    """분석 결과 저장 (Stage 7).
    
    Args:
        df: 분석 결과 DataFrame
        analysis_type: 분석 유형 (예: 'statistics', 'centrality', 'community')
        output_dir: 출력 디렉토리 (기본값: data/results/)
        filename: 파일명 (None이면 analysis_type 사용)
        
    Returns:
        저장된 파일 경로
    """
    if filename is None:
        filename = f"{analysis_type}.parquet"
    
    output_path = Path(output_dir) / filename
    return save_to_parquet(df, output_path, metadata={"analysis_type": analysis_type})
