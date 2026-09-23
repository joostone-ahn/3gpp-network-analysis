"""
Pytest 공통 Fixtures 및 설정.

모든 테스트에서 공유하는 fixture들을 정의한다.
"""

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import pytest

from src.utils.config_loader import (
    CollectorConfig,
    CollectorTarget,
    PreprocessingConfig,
    SourceCleaningConfig,
    NormalizationConfig,
    DateRange,
    NetworkConfig,
    AnalysisConfig,
    load_config,
)


# =============================================================================
# 공통 Fixtures
# =============================================================================


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """임시 데이터 디렉토리 생성.
    
    data/raw, data/interim, data/processed, data/results 디렉토리를 생성한다.
    """
    data_dir = tmp_path / "data"
    (data_dir / "raw").mkdir(parents=True)
    (data_dir / "interim").mkdir(parents=True)
    (data_dir / "processed").mkdir(parents=True)
    (data_dir / "results").mkdir(parents=True)
    (data_dir / "reference").mkdir(parents=True)
    return data_dir


@pytest.fixture
def project_config_dir() -> Path:
    """프로젝트의 실제 config 디렉토리."""
    return Path(__file__).parent.parent / "config"


# =============================================================================
# 설정 관련 Fixtures
# =============================================================================


@pytest.fixture
def collector_config() -> CollectorConfig:
    """테스트용 Collector 설정."""
    return CollectorConfig(
        ftp_host="ftp.test.org",
        ftp_base_path_template="/tsg_{tsg_lower}/TSG_{tsg}/TSGR_{mtg}/Docs/",
        targets=[
            CollectorTarget(tsg="RAN", min_meeting=69, wg_list=["TSG", "WG1", "WG2"]),
            CollectorTarget(tsg="SA", min_meeting=69, wg_list=["TSG", "WG1"]),
            CollectorTarget(tsg="CT", min_meeting=69, wg_list=["TSG"]),
        ],
        max_retry=2,
        retry_delay=0,
    )


@pytest.fixture
def preprocessing_config() -> PreprocessingConfig:
    """테스트용 Preprocessing 설정."""
    return PreprocessingConfig(
        title_exclude_patterns=[
            "LS on", "LS to", "LS Reply", "Reply LS",
            "LS in relation to", "LS for", "LS regarding",
            "LS response", "LS out", "LS answer", "LS about",
            "LS-Replay", "CR pack"
        ],
        source_cleaning=SourceCleaningConfig(
            special_replacements={"CMCC": "China Mobile"},
            remove_characters=["[", "]", "."],
            add_word_boundary_spaces=True,
        ),
        membership_normalization=NormalizationConfig(
            stopwords=[" Ltd.", " Inc.", " GmbH", " Corporation"],
            countries=[" Germany", " USA", " Korea", " Japan"],
            removes=["Beijing", "Nanjing"],
            replaces={"HuaWei": "Huawei", "Guangdong OPPO": "OPPO"},
            brackets_pattern=r"\s\(",
            startswith_exceptions=["BTL"],
            suffix=[" Software", " Research"],
            prefix=["Hangzhou ", "Shanghai "],
        ),
        wi_delimiters=[","],
        wi_exclude_patterns=["TEI", "DUMMY"],
        date_range=DateRange(min_year=2015),
    )


@pytest.fixture
def network_config() -> NetworkConfig:
    """테스트용 Network 설정."""
    return NetworkConfig(
        thresholds=[0, 1, 2, 3, 4, 5],
        time_units=["year", "release"],
        tsg_groups=["ALL", "RAN", "SA", "CT"],
    )


@pytest.fixture
def analysis_config() -> AnalysisConfig:
    """테스트용 Analysis 설정."""
    return AnalysisConfig(
        louvain_seed=42,
        eigenvector_max_iter=1000,
        random_network_samples=10,  # 테스트에서는 작은 값 사용
    )


# =============================================================================
# 샘플 데이터 Fixtures
# =============================================================================


@pytest.fixture
def sample_parsed_df() -> pd.DataFrame:
    """테스트용 파싱 완료 DataFrame.
    
    Parser 모듈의 출력을 시뮬레이션한다.
    """
    return pd.DataFrame({
        "TDoc": ["R1-001", "R1-002", "R1-003", "R1-004"],
        "Title": ["Test Doc 1", "Test Doc 2", "Test Doc 3", "LS on Test"],
        "Source": [
            "Samsung Electronics, Nokia",
            "Samsung Electronics",
            "Nokia, Huawei",
            "Chair",
        ],
        "Related WIs": ["WI_A", "WI_A, WI_B", "WI_B", "WI_C"],
        "Release": [17, 17, 17, 17],
        "Uploaded": pd.to_datetime([
            "2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04"
        ]),
        "TSG": ["RAN", "RAN", "RAN", "RAN"],
        "WG": ["WG1", "WG1", "WG1", "WG1"],
        "MTG": [100, 100, 100, 100],
    })


@pytest.fixture
def sample_membership_df() -> pd.DataFrame:
    """테스트용 멤버십 DataFrame."""
    return pd.DataFrame({
        "simple": [
            "Samsung Electronics",
            "Nokia",
            "Huawei",
            "Ericsson",
            "China Mobile",
            "Qualcomm",
            "Intel",
            "Apple",
        ]
    })


@pytest.fixture
def sample_manual_mapping_df() -> pd.DataFrame:
    """테스트용 수작업 매핑 DataFrame."""
    return pd.DataFrame({
        "alias": ["Samsung", "HW", "CMCC"],
        "standard_name": ["Samsung Electronics", "Huawei", "China Mobile"],
    })


@pytest.fixture
def sample_preprocessed_df() -> pd.DataFrame:
    """테스트용 전처리 완료 DataFrame.
    
    Preprocessor 모듈의 출력을 시뮬레이션한다.
    """
    return pd.DataFrame({
        "TDoc": ["R1-001", "R1-001", "R1-002", "R1-003", "R1-003"],
        "Title": ["Test Doc 1", "Test Doc 1", "Test Doc 2", "Test Doc 3", "Test Doc 3"],
        "company": ["Samsung Electronics", "Nokia", "Samsung Electronics", "Nokia", "Huawei"],
        "Work_Item": ["WI_A", "WI_A", "WI_A", "WI_B", "WI_B"],
        "Release": [17, 17, 17, 17, 17],
        "Year": [2023, 2023, 2023, 2023, 2023],
        "Quarter": ["2023Q1", "2023Q1", "2023Q1", "2023Q1", "2023Q1"],
        "TSG": ["RAN", "RAN", "RAN", "RAN", "RAN"],
        "WG": ["WG1", "WG1", "WG1", "WG1", "WG1"],
    })


@pytest.fixture
def sample_edges_df() -> pd.DataFrame:
    """테스트용 Edge list DataFrame."""
    return pd.DataFrame({
        "Source": ["Nokia", "Huawei", "Nokia"],
        "Target": ["Samsung Electronics", "Samsung Electronics", "Huawei"],
        "Weight": [2, 1, 1],
    })


# =============================================================================
# 실제 설정 로드 Fixtures (통합 테스트용)
# =============================================================================


@pytest.fixture
def real_collector_config() -> CollectorConfig:
    """실제 collector.yaml 로드."""
    return load_config("collector")


@pytest.fixture
def real_preprocessing_config() -> PreprocessingConfig:
    """실제 preprocessing.yaml 로드."""
    return load_config("preprocessing")


@pytest.fixture
def real_network_config() -> NetworkConfig:
    """실제 network.yaml 로드."""
    return load_config("network")


@pytest.fixture
def real_analysis_config() -> AnalysisConfig:
    """실제 analysis.yaml 로드."""
    return load_config("analysis")
