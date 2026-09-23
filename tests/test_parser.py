"""
TDocParser 테스트 모듈

TDocParser 클래스의 파싱 기능을 검증하는 단위 테스트 및 Property-based 테스트.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
Property Tests: 17.1, 17.2, 17.3
"""

import tempfile
from pathlib import Path
from typing import Generator, List, Optional

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from src.parser.xlsx_parser import (
    ParseStats,
    TDocParser,
    load_parsed_tdocs,
    save_parsed_tdocs,
)
from src.utils.parquet_utils import (
    load_from_parquet,
    save_to_parquet,
    verify_round_trip,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def parser() -> TDocParser:
    """TDocParser 인스턴스 생성."""
    return TDocParser()


@pytest.fixture
def sample_tdoc_data() -> pd.DataFrame:
    """테스트용 TDoc 데이터 생성."""
    return pd.DataFrame({
        'TDoc': ['R1-2301234', 'R1-2301235', 'R1-2301236'],
        'Title': ['Test Contribution 1', 'Test Contribution 2', 'Test CR Pack'],
        'Source': ['Samsung Electronics', 'Nokia, Huawei', 'Ericsson'],
        'Related WIs': ['NR_XYZ', 'NR_ABC, NR_DEF', 'TEI'],
        'Release': ['Rel-17', 'Release 18', 'R15'],
        'Uploaded': pd.to_datetime(['2023-01-15', '2023-02-20', '2023-03-25']),
    })


@pytest.fixture
def temp_xlsx_dir() -> Generator[Path, None, None]:
    """임시 xlsx 파일 디렉토리 생성."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_test_xlsx(
    dir_path: Path,
    filename: str,
    data: pd.DataFrame,
    tsg: str = "RAN"
) -> Path:
    """테스트용 xlsx 파일 생성.
    
    Args:
        dir_path: 디렉토리 경로
        filename: 파일명
        data: DataFrame 데이터
        tsg: TSG 그룹명 (하위 디렉토리 생성용)
        
    Returns:
        생성된 파일 경로
    """
    tsg_dir = dir_path / tsg
    tsg_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = tsg_dir / filename
    data.to_excel(file_path, index=False, engine='openpyxl')
    return file_path


# =============================================================================
# extract_release 테스트 (요구사항 2.2)
# =============================================================================


class TestExtractRelease:
    """extract_release() 메서드 테스트."""
    
    def test_rel_dash_format(self, parser: TDocParser) -> None:
        """Rel-15 형식 테스트."""
        assert parser.extract_release("Rel-15") == 15
        assert parser.extract_release("Rel-17") == 17
        assert parser.extract_release("Rel-18") == 18
    
    def test_release_space_format(self, parser: TDocParser) -> None:
        """Release 16 형식 테스트."""
        assert parser.extract_release("Release 16") == 16
        assert parser.extract_release("Release 17") == 17
    
    def test_r_prefix_format(self, parser: TDocParser) -> None:
        """R17 형식 테스트."""
        assert parser.extract_release("R15") == 15
        assert parser.extract_release("R17") == 17
    
    def test_lowercase_format(self, parser: TDocParser) -> None:
        """소문자 형식 테스트 (rel15)."""
        assert parser.extract_release("rel15") == 15
        assert parser.extract_release("release16") == 16
    
    def test_empty_string(self, parser: TDocParser) -> None:
        """빈 문자열 테스트."""
        assert parser.extract_release("") is None
        assert parser.extract_release("   ") is None
    
    def test_none_value(self, parser: TDocParser) -> None:
        """None 값 테스트."""
        assert parser.extract_release(None) is None
    
    def test_nan_value(self, parser: TDocParser) -> None:
        """NaN 값 테스트."""
        import numpy as np
        assert parser.extract_release(np.nan) is None
        assert parser.extract_release(pd.NA) is None
    
    def test_no_number(self, parser: TDocParser) -> None:
        """숫자 없는 문자열 테스트."""
        assert parser.extract_release("Release") is None
        assert parser.extract_release("Rel-") is None
    
    def test_numeric_input(self, parser: TDocParser) -> None:
        """숫자 입력 테스트."""
        assert parser.extract_release(15) == 15
        assert parser.extract_release(17) == 17


# =============================================================================
# 파일명 패턴 및 메타데이터 추출 테스트 (요구사항 2.3, 2.5)
# =============================================================================


class TestFilenamePattern:
    """파일명 패턴 매칭 및 메타데이터 추출 테스트."""
    
    def test_tsg_plenary_pattern(self, parser: TDocParser) -> None:
        """TSG 총회 파일명 패턴 (TDoc_List_Meeting_RAN#100.xlsx)."""
        path = Path("/data/raw/RAN/TDoc_List_Meeting_RAN#100.xlsx")
        metadata = parser._extract_metadata_from_path(path)
        
        assert metadata is not None
        assert metadata['tsg'] == "RAN"
        assert metadata['wg'] == "TSG"
        assert metadata['mtg'] == 100
    
    def test_wg_pattern(self, parser: TDocParser) -> None:
        """WG 파일명 패턴 (TDoc_List_Meeting_RAN1#150.xlsx)."""
        path = Path("/data/raw/RAN/TDoc_List_Meeting_RAN1#150.xlsx")
        metadata = parser._extract_metadata_from_path(path)
        
        assert metadata is not None
        assert metadata['tsg'] == "RAN"
        assert metadata['wg'] == "WG1"
        assert metadata['mtg'] == 150
    
    def test_sa_tsg_pattern(self, parser: TDocParser) -> None:
        """SA TSG 파일명 패턴."""
        path = Path("/data/raw/SA/TDoc_List_Meeting_SA#90.xlsx")
        metadata = parser._extract_metadata_from_path(path)
        
        assert metadata is not None
        assert metadata['tsg'] == "SA"
        assert metadata['wg'] == "TSG"
        assert metadata['mtg'] == 90
    
    def test_ct_wg_pattern(self, parser: TDocParser) -> None:
        """CT WG 파일명 패턴."""
        path = Path("/data/raw/CT/TDoc_List_Meeting_CT4#200.xlsx")
        metadata = parser._extract_metadata_from_path(path)
        
        assert metadata is not None
        assert metadata['tsg'] == "CT"
        assert metadata['wg'] == "WG4"
        assert metadata['mtg'] == 200
    
    def test_e_meeting_suffix(self, parser: TDocParser) -> None:
        """e-meeting 접미사 패턴 (TDoc_List_Meeting_RAN#100-e.xlsx)."""
        path = Path("/data/raw/RAN/TDoc_List_Meeting_RAN#100-e.xlsx")
        metadata = parser._extract_metadata_from_path(path)
        
        assert metadata is not None
        assert metadata['tsg'] == "RAN"
        assert metadata['wg'] == "TSG"
        assert metadata['mtg'] == 100
    
    def test_invalid_pattern(self, parser: TDocParser) -> None:
        """잘못된 패턴 테스트."""
        # 패턴 불일치 케이스들 - TDoc_List_Meeting_xxx#nnn 형태가 아닌 것들
        invalid_paths = [
            Path("/data/raw/RAN/random_file.xlsx"),
            Path("/data/raw/RAN/TDoc_List.xlsx"),
            Path("/data/raw/RAN/SomeOther_Meeting_RAN#100.xlsx"),  # TDoc_List로 시작 안함
        ]
        
        for path in invalid_paths:
            metadata = parser._extract_metadata_from_path(path)
            assert metadata is None, f"Should be None for {path}"


# =============================================================================
# parse_file 테스트 (요구사항 2.1, 2.4)
# =============================================================================


class TestParseFile:
    """parse_file() 메서드 테스트."""
    
    def test_successful_parse(
        self,
        parser: TDocParser,
        sample_tdoc_data: pd.DataFrame,
        temp_xlsx_dir: Path
    ) -> None:
        """정상 파싱 테스트."""
        file_path = create_test_xlsx(
            temp_xlsx_dir,
            "TDoc_List_Meeting_RAN#100.xlsx",
            sample_tdoc_data,
            "RAN"
        )
        
        result = parser.parse_file(file_path)
        
        assert result is not None
        assert len(result) == 3
        
        # 출력 컬럼 확인
        for col in TDocParser.OUTPUT_COLUMNS:
            assert col in result.columns
        
        # 메타데이터 확인
        assert all(result['TSG'] == 'RAN')
        assert all(result['WG'] == 'TSG')
        assert all(result['MTG'] == 100)
        
        # Release 변환 확인
        assert result['Release'].iloc[0] == 17
        assert result['Release'].iloc[1] == 18
        assert result['Release'].iloc[2] == 15
    
    def test_missing_required_columns(
        self,
        parser: TDocParser,
        temp_xlsx_dir: Path
    ) -> None:
        """필수 컬럼 누락 테스트 (요구사항 2.4)."""
        # Source 컬럼 누락
        data = pd.DataFrame({
            'TDoc': ['R1-2301234'],
            'Title': ['Test'],
            # 'Source' 누락
        })
        
        file_path = create_test_xlsx(
            temp_xlsx_dir,
            "TDoc_List_Meeting_RAN#100.xlsx",
            data,
            "RAN"
        )
        
        result = parser.parse_file(file_path)
        
        assert result is None
        stats = parser.get_stats()
        assert len(stats.files_with_missing_columns) == 1
        assert 'Source' in stats.files_with_missing_columns[0]['missing_columns']
    
    def test_file_not_found(self, parser: TDocParser) -> None:
        """존재하지 않는 파일 테스트."""
        result = parser.parse_file(Path("/nonexistent/file.xlsx"))
        assert result is None
    
    def test_pattern_mismatch(
        self,
        parser: TDocParser,
        sample_tdoc_data: pd.DataFrame,
        temp_xlsx_dir: Path
    ) -> None:
        """파일명 패턴 불일치 테스트 (요구사항 2.5)."""
        # 잘못된 파일명
        tsg_dir = temp_xlsx_dir / "RAN"
        tsg_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = tsg_dir / "random_file.xlsx"
        sample_tdoc_data.to_excel(file_path, index=False, engine='openpyxl')
        
        result = parser.parse_file(file_path)
        
        assert result is None
        stats = parser.get_stats()
        assert len(stats.files_with_pattern_mismatch) == 1


# =============================================================================
# parse_all 테스트
# =============================================================================


class TestParseAll:
    """parse_all() 메서드 테스트."""
    
    def test_multiple_files(
        self,
        parser: TDocParser,
        sample_tdoc_data: pd.DataFrame,
        temp_xlsx_dir: Path
    ) -> None:
        """여러 파일 병합 테스트."""
        # RAN 파일
        create_test_xlsx(
            temp_xlsx_dir,
            "TDoc_List_Meeting_RAN#100.xlsx",
            sample_tdoc_data,
            "RAN"
        )
        
        # SA 파일
        create_test_xlsx(
            temp_xlsx_dir,
            "TDoc_List_Meeting_SA#90.xlsx",
            sample_tdoc_data,
            "SA"
        )
        
        result = parser.parse_all(temp_xlsx_dir)
        
        assert len(result) == 6  # 3 + 3
        assert set(result['TSG'].unique()) == {'RAN', 'SA'}
        
        stats = parser.get_stats()
        assert stats.total_files == 2
        assert stats.successful_files == 2
        assert stats.total_rows == 6
    
    def test_empty_directory(
        self,
        parser: TDocParser,
        temp_xlsx_dir: Path
    ) -> None:
        """빈 디렉토리 테스트."""
        result = parser.parse_all(temp_xlsx_dir)
        
        assert len(result) == 0
        assert list(result.columns) == TDocParser.OUTPUT_COLUMNS
    
    def test_nonexistent_directory(self, parser: TDocParser) -> None:
        """존재하지 않는 디렉토리 테스트."""
        result = parser.parse_all(Path("/nonexistent/directory"))
        
        assert len(result) == 0
        assert list(result.columns) == TDocParser.OUTPUT_COLUMNS


# =============================================================================
# Parquet round-trip 테스트 (요구사항 2.6)
# =============================================================================


class TestParquetRoundTrip:
    """Parquet 저장/로드 round-trip 테스트."""
    
    def test_round_trip_equality(
        self,
        parser: TDocParser,
        sample_tdoc_data: pd.DataFrame,
        temp_xlsx_dir: Path
    ) -> None:
        """저장 후 로드한 데이터가 원본과 동등한지 테스트."""
        # xlsx 파일 생성 및 파싱
        create_test_xlsx(
            temp_xlsx_dir,
            "TDoc_List_Meeting_RAN#100.xlsx",
            sample_tdoc_data,
            "RAN"
        )
        
        original_df = parser.parse_all(temp_xlsx_dir)
        
        # Parquet 저장
        parquet_path = temp_xlsx_dir / "test.parquet"
        save_parsed_tdocs(original_df, parquet_path)
        
        # Parquet 로드
        loaded_df = load_parsed_tdocs(parquet_path)
        
        # 동등성 검증
        pd.testing.assert_frame_equal(original_df, loaded_df)
    
    def test_load_nonexistent_file(self, temp_xlsx_dir: Path) -> None:
        """존재하지 않는 Parquet 파일 로드 테스트."""
        with pytest.raises(FileNotFoundError):
            load_parsed_tdocs(temp_xlsx_dir / "nonexistent.parquet")


# =============================================================================
# 컬럼 정규화 테스트
# =============================================================================


class TestColumnNormalization:
    """컬럼명 정규화 테스트."""
    
    def test_case_insensitive_columns(
        self,
        parser: TDocParser,
        temp_xlsx_dir: Path
    ) -> None:
        """대소문자 무시 컬럼 매핑 테스트."""
        # 다양한 대소문자 컬럼명
        data = pd.DataFrame({
            'tdoc': ['R1-2301234'],
            'TITLE': ['Test'],
            'SOURCE': ['Samsung'],
            'Related WIs': ['NR_XYZ'],
            'release': ['Rel-17'],
            'UPLOADED': pd.to_datetime(['2023-01-15']),
        })
        
        file_path = create_test_xlsx(
            temp_xlsx_dir,
            "TDoc_List_Meeting_RAN#100.xlsx",
            data,
            "RAN"
        )
        
        result = parser.parse_file(file_path)
        
        assert result is not None
        # 표준화된 컬럼명 확인
        assert 'TDoc' in result.columns
        assert 'Title' in result.columns
        assert 'Source' in result.columns


# =============================================================================
# Property-Based Tests (Hypothesis)
# =============================================================================

# Custom Strategies for generating test data
# -----------------------------------------------------------------------------

# Strategy for generating Release strings in various formats
release_string_strategy = st.one_of(
    st.builds(lambda n: f"Rel-{n}", st.integers(min_value=1, max_value=99)),
    st.builds(lambda n: f"Release {n}", st.integers(min_value=1, max_value=99)),
    st.builds(lambda n: f"R{n}", st.integers(min_value=1, max_value=99)),
    st.builds(lambda n: f"rel{n}", st.integers(min_value=1, max_value=99)),
    st.builds(lambda n: f"release{n}", st.integers(min_value=1, max_value=99)),
    st.builds(lambda n: f"REL-{n}", st.integers(min_value=1, max_value=99)),
)

# Strategy for generating valid Release numbers
valid_release_number = st.integers(min_value=1, max_value=99)

# Strategy for generating TDoc IDs
tdoc_id_strategy = st.builds(
    lambda tsg, num: f"{tsg}-{num:07d}",
    st.sampled_from(["R1", "R2", "R3", "R4", "R5", "R6", "S1", "S2", "S3", "S4", "S5", "S6", "C1", "C3", "C4", "C6"]),
    st.integers(min_value=2300000, max_value=2399999)
)

# Strategy for generating company names
company_name_strategy = st.sampled_from([
    "Samsung Electronics", "Nokia", "Huawei", "Ericsson", "Qualcomm",
    "Intel", "Apple", "OPPO", "Xiaomi", "vivo", "ZTE", "LG Electronics",
    "NTT Docomo", "China Mobile", "AT&T", "Verizon", "Deutsche Telekom"
])

# Strategy for generating Work Item IDs
work_item_strategy = st.builds(
    lambda prefix, suffix: f"{prefix}_{suffix}",
    st.sampled_from(["NR", "LTE", "FS", "TEI", "UID"]),
    st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=3, max_size=10)
)

# Strategy for generating Title strings
title_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
    min_size=5,
    max_size=200
)

# Strategy for generating TSG groups
tsg_strategy = st.sampled_from(["RAN", "SA", "CT"])

# Strategy for generating WG identifiers
wg_strategy = st.sampled_from(["TSG", "WG1", "WG2", "WG3", "WG4", "WG5", "WG6"])

# Strategy for generating meeting numbers
mtg_strategy = st.integers(min_value=69, max_value=200)


@st.composite
def dataframe_with_tdocs(draw, min_rows: int = 1, max_rows: int = 100) -> pd.DataFrame:
    """Generate a valid TDoc DataFrame for testing.
    
    **Validates: Requirements 2.1 (DataFrame schema)**
    
    Args:
        draw: Hypothesis draw function
        min_rows: Minimum number of rows to generate
        max_rows: Maximum number of rows to generate
        
    Returns:
        pd.DataFrame with TDoc data conforming to OUTPUT_COLUMNS schema
    """
    n_rows = draw(st.integers(min_value=min_rows, max_value=max_rows))
    
    data = {
        'TDoc': [draw(tdoc_id_strategy) for _ in range(n_rows)],
        'Title': [draw(title_strategy) for _ in range(n_rows)],
        'Source': [draw(company_name_strategy) for _ in range(n_rows)],
        'Related WIs': [draw(work_item_strategy) for _ in range(n_rows)],
        'Release': [draw(st.integers(min_value=15, max_value=20)) for _ in range(n_rows)],
        'Uploaded': pd.to_datetime([
            draw(st.dates(min_value=pd.Timestamp('2020-01-01').date(), 
                          max_value=pd.Timestamp('2025-12-31').date()))
            for _ in range(n_rows)
        ]),
        'TSG': [draw(tsg_strategy) for _ in range(n_rows)],
        'WG': [draw(wg_strategy) for _ in range(n_rows)],
        'MTG': [draw(mtg_strategy) for _ in range(n_rows)],
    }
    
    return pd.DataFrame(data)


# =============================================================================
# Property 3: DataFrame Schema Consistency Test
# =============================================================================

class TestDataFrameSchemaConsistencyProperty:
    """
    **Validates: Requirements 2.1**
    
    Property 3: DataFrame 스키마 일관성 테스트
    
    파싱된 DataFrame은 항상 OUTPUT_COLUMNS에 정의된 컬럼을 포함해야 한다.
    """
    
    @given(data=st.data())
    @settings(max_examples=50, deadline=None)
    def test_schema_consistency_after_parse(self, data: st.DataObject) -> None:
        """파싱 후 DataFrame 스키마가 OUTPUT_COLUMNS와 일치해야 한다.
        
        **Validates: Requirements 2.1**
        
        Property:
            For any valid TDoc xlsx file, parse_file() returns a DataFrame
            with exactly the columns specified in OUTPUT_COLUMNS.
        """
        parser = TDocParser()
        
        # Generate test data
        n_rows = data.draw(st.integers(min_value=1, max_value=20))
        release_values = [data.draw(release_string_strategy) for _ in range(n_rows)]
        
        test_data = pd.DataFrame({
            'TDoc': [data.draw(tdoc_id_strategy) for _ in range(n_rows)],
            'Title': [f"Test Contribution {i}" for i in range(n_rows)],
            'Source': [data.draw(company_name_strategy) for _ in range(n_rows)],
            'Related WIs': [data.draw(work_item_strategy) for _ in range(n_rows)],
            'Release': release_values,
            'Uploaded': pd.to_datetime(['2023-01-15'] * n_rows),
        })
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            tsg = data.draw(tsg_strategy)
            mtg = data.draw(mtg_strategy)
            
            tsg_dir = tmpdir_path / tsg
            tsg_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = tsg_dir / f"TDoc_List_Meeting_{tsg}#{mtg}.xlsx"
            test_data.to_excel(file_path, index=False, engine='openpyxl')
            
            result = parser.parse_file(file_path)
            
            assert result is not None, "Parsing should succeed for valid data"
            
            # Property: Schema matches OUTPUT_COLUMNS exactly
            assert list(result.columns) == TDocParser.OUTPUT_COLUMNS, \
                f"Schema mismatch: got {list(result.columns)}, expected {TDocParser.OUTPUT_COLUMNS}"
            
            # Property: Row count is preserved
            assert len(result) == n_rows, \
                f"Row count mismatch: got {len(result)}, expected {n_rows}"

    @given(tsg=tsg_strategy, wg=wg_strategy, mtg=mtg_strategy)
    @settings(max_examples=30, deadline=None)
    def test_metadata_columns_populated(
        self, tsg: str, wg: str, mtg: int
    ) -> None:
        """메타데이터 컬럼(TSG, WG, MTG)이 올바르게 채워져야 한다.
        
        **Validates: Requirements 2.3**
        
        Property:
            For any parsed file, TSG/WG/MTG columns are populated from filename.
        """
        parser = TDocParser()
        
        test_data = pd.DataFrame({
            'TDoc': ['R1-2301234'],
            'Title': ['Test'],
            'Source': ['Samsung'],
            'Related WIs': ['NR_XYZ'],
            'Release': ['Rel-17'],
            'Uploaded': pd.to_datetime(['2023-01-15']),
        })
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            tsg_dir = tmpdir_path / tsg
            tsg_dir.mkdir(parents=True, exist_ok=True)
            
            # Determine group name for filename
            if wg == "TSG":
                group_name = tsg  # e.g., "RAN"
            else:
                wg_num = wg.replace("WG", "")  # e.g., "WG1" -> "1"
                group_name = f"{tsg}{wg_num}"  # e.g., "RAN1"
            
            file_path = tsg_dir / f"TDoc_List_Meeting_{group_name}#{mtg}.xlsx"
            test_data.to_excel(file_path, index=False, engine='openpyxl')
            
            result = parser.parse_file(file_path)
            
            assert result is not None
            
            # Property: Metadata is correctly extracted from filename
            assert all(result['TSG'] == tsg), f"TSG should be {tsg}"
            assert all(result['WG'] == wg), f"WG should be {wg}"
            assert all(result['MTG'] == mtg), f"MTG should be {mtg}"


# =============================================================================
# Property 4: Release Parsing Accuracy Test
# =============================================================================

class TestReleaseParsingProperty:
    """
    **Validates: Requirements 2.2**
    
    Property 4: Release 파싱 정확성 테스트
    
    extract_release()는 다양한 형식의 Release 문자열에서 정수를 정확히 추출해야 한다.
    """
    
    @given(release_num=valid_release_number)
    @settings(max_examples=100, deadline=None)
    def test_rel_dash_format_extraction(self, release_num: int) -> None:
        """Rel-XX 형식에서 숫자 추출.
        
        **Validates: Requirements 2.2**
        
        Property:
            extract_release(f"Rel-{n}") == n for all positive integers n
        """
        parser = TDocParser()
        result = parser.extract_release(f"Rel-{release_num}")
        assert result == release_num, f"Expected {release_num}, got {result}"
    
    @given(release_num=valid_release_number)
    @settings(max_examples=100, deadline=None)
    def test_release_space_format_extraction(self, release_num: int) -> None:
        """Release XX 형식에서 숫자 추출.
        
        **Validates: Requirements 2.2**
        
        Property:
            extract_release(f"Release {n}") == n for all positive integers n
        """
        parser = TDocParser()
        result = parser.extract_release(f"Release {release_num}")
        assert result == release_num, f"Expected {release_num}, got {result}"
    
    @given(release_num=valid_release_number)
    @settings(max_examples=100, deadline=None)
    def test_r_prefix_format_extraction(self, release_num: int) -> None:
        """RXX 형식에서 숫자 추출.
        
        **Validates: Requirements 2.2**
        
        Property:
            extract_release(f"R{n}") == n for all positive integers n
        """
        parser = TDocParser()
        result = parser.extract_release(f"R{release_num}")
        assert result == release_num, f"Expected {release_num}, got {result}"
    
    @given(release_num=valid_release_number)
    @settings(max_examples=100, deadline=None)
    def test_lowercase_format_extraction(self, release_num: int) -> None:
        """소문자 형식(relXX)에서 숫자 추출.
        
        **Validates: Requirements 2.2**
        
        Property:
            extract_release(f"rel{n}") == n for all positive integers n
        """
        parser = TDocParser()
        result = parser.extract_release(f"rel{release_num}")
        assert result == release_num, f"Expected {release_num}, got {result}"
    
    @given(release_str=release_string_strategy)
    @settings(max_examples=100, deadline=None)
    def test_extraction_returns_positive_integer(self, release_str: str) -> None:
        """모든 유효한 Release 문자열은 양의 정수를 반환해야 한다.
        
        **Validates: Requirements 2.2**
        
        Property:
            For any valid release string, the result is a positive integer.
        """
        parser = TDocParser()
        result = parser.extract_release(release_str)
        
        assert result is not None, f"Should extract number from '{release_str}'"
        assert isinstance(result, int), f"Result should be int, got {type(result)}"
        assert result > 0, f"Result should be positive, got {result}"
    
    @given(text=st.text(alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ '))
    @settings(max_examples=50, deadline=None)
    def test_no_number_returns_none(self, text: str) -> None:
        """숫자가 없는 문자열은 None을 반환해야 한다.
        
        **Validates: Requirements 2.2**
        
        Property:
            For strings without digits, extract_release returns None.
        """
        parser = TDocParser()
        result = parser.extract_release(text)
        
        # If text contains no digits, result should be None
        if not any(c.isdigit() for c in text):
            assert result is None, f"Should return None for '{text}', got {result}"

    @given(release_num=valid_release_number)
    @settings(max_examples=50, deadline=None)
    def test_first_number_extraction(self, release_num: int) -> None:
        """첫 번째 숫자만 추출된다.
        
        **Validates: Requirements 2.2**
        
        Property:
            extract_release extracts the FIRST number from the string
            (consistent with original notebook behavior: str.extract(r'(\\d+)'))
        """
        parser = TDocParser()
        
        # Test cases with multiple numbers
        test_cases = [
            (f"Rel-{release_num} (version 2)", release_num),
            (f"Release {release_num}.0", release_num),
            (f"v{release_num}.1.2", release_num),
        ]
        
        for release_str, expected in test_cases:
            result = parser.extract_release(release_str)
            assert result == expected, \
                f"Expected {expected} from '{release_str}', got {result}"


# =============================================================================
# Property 5: Parquet Round-Trip Test
# =============================================================================

class TestParquetRoundTripProperty:
    """
    **Validates: Requirements 2.6, 17.3**
    
    Property 5: Parquet round-trip 테스트
    
    DataFrame을 Parquet으로 저장하고 다시 로드했을 때 원본과 동등해야 한다.
    """
    
    @given(df=dataframe_with_tdocs(min_rows=1, max_rows=50))
    @settings(max_examples=30, deadline=None)
    def test_parquet_round_trip_preserves_data(self, df: pd.DataFrame) -> None:
        """Parquet 저장/로드 후 데이터가 동등해야 한다.
        
        **Validates: Requirements 2.6, 17.3**
        
        Property:
            For any valid DataFrame df, 
            save_to_parquet(df, path) followed by load_from_parquet(path) 
            returns a DataFrame equal to df.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / "test_roundtrip.parquet"
            
            # Save to Parquet
            save_to_parquet(df, parquet_path)
            
            # Load from Parquet
            loaded_df = load_from_parquet(parquet_path)
            
            # Property: Round-trip preserves data
            pd.testing.assert_frame_equal(
                df.reset_index(drop=True),
                loaded_df.reset_index(drop=True),
                check_dtype=True
            )
    
    @given(df=dataframe_with_tdocs(min_rows=1, max_rows=50))
    @settings(max_examples=30, deadline=None)
    def test_parquet_round_trip_preserves_dtypes(self, df: pd.DataFrame) -> None:
        """Parquet round-trip 후 데이터 타입이 보존되어야 한다.
        
        **Validates: Requirements 2.6**
        
        Property:
            Column data types are preserved after round-trip.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / "test_dtypes.parquet"
            
            original_dtypes = df.dtypes.to_dict()
            
            save_to_parquet(df, parquet_path)
            loaded_df = load_from_parquet(parquet_path)
            
            # Check dtypes (some flexibility for datetime precision)
            for col in df.columns:
                orig_dtype = original_dtypes[col]
                loaded_dtype = loaded_df[col].dtype
                
                # Allow for datetime64 precision differences
                if pd.api.types.is_datetime64_any_dtype(orig_dtype):
                    assert pd.api.types.is_datetime64_any_dtype(loaded_dtype), \
                        f"Column {col}: expected datetime, got {loaded_dtype}"
                else:
                    # For non-datetime columns, dtypes should match
                    assert orig_dtype == loaded_dtype or \
                           str(orig_dtype) == str(loaded_dtype), \
                        f"Column {col}: dtype mismatch {orig_dtype} != {loaded_dtype}"
    
    @given(df=dataframe_with_tdocs(min_rows=1, max_rows=30))
    @settings(max_examples=20, deadline=None)
    def test_parquet_round_trip_preserves_row_count(self, df: pd.DataFrame) -> None:
        """Parquet round-trip 후 행 수가 보존되어야 한다.
        
        **Validates: Requirements 2.6**
        
        Property:
            len(loaded_df) == len(original_df)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / "test_rowcount.parquet"
            
            original_row_count = len(df)
            
            save_to_parquet(df, parquet_path)
            loaded_df = load_from_parquet(parquet_path)
            
            assert len(loaded_df) == original_row_count, \
                f"Row count mismatch: expected {original_row_count}, got {len(loaded_df)}"
    
    @given(df=dataframe_with_tdocs(min_rows=1, max_rows=30))
    @settings(max_examples=20, deadline=None)
    def test_parquet_round_trip_preserves_column_order(self, df: pd.DataFrame) -> None:
        """Parquet round-trip 후 컬럼 순서가 보존되어야 한다.
        
        **Validates: Requirements 2.6**
        
        Property:
            list(loaded_df.columns) == list(original_df.columns)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / "test_colorder.parquet"
            
            original_columns = list(df.columns)
            
            save_to_parquet(df, parquet_path)
            loaded_df = load_from_parquet(parquet_path)
            
            assert list(loaded_df.columns) == original_columns, \
                f"Column order mismatch: expected {original_columns}, got {list(loaded_df.columns)}"

    @given(st.data())
    @settings(max_examples=20, deadline=None)
    def test_verify_round_trip_utility(self, data: st.DataObject) -> None:
        """verify_round_trip 유틸리티 함수가 올바르게 동작해야 한다.
        
        **Validates: Requirements 2.6, 17.3**
        
        Property:
            verify_round_trip returns True for valid DataFrames.
        """
        df = data.draw(dataframe_with_tdocs(min_rows=1, max_rows=20))
        
        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / "test_verify.parquet"
            
            result = verify_round_trip(df, parquet_path)
            
            assert result is True, "verify_round_trip should return True for valid data"


# =============================================================================
# 추가 Property Tests - Edge Cases
# =============================================================================

class TestParserEdgeCasesProperty:
    """Parser 엣지 케이스에 대한 Property 테스트."""
    
    @given(st.data())
    @settings(max_examples=30, deadline=None)
    def test_empty_dataframe_round_trip(self, data: st.DataObject) -> None:
        """빈 DataFrame의 round-trip이 성공해야 한다.
        
        Property:
            Empty DataFrames with correct schema can round-trip.
        """
        # Create empty DataFrame with OUTPUT_COLUMNS schema
        empty_df = pd.DataFrame(columns=TDocParser.OUTPUT_COLUMNS)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / "empty.parquet"
            
            save_to_parquet(empty_df, parquet_path)
            loaded_df = load_from_parquet(parquet_path)
            
            assert len(loaded_df) == 0
            assert list(loaded_df.columns) == list(empty_df.columns)
    
    @given(release_num=st.integers(min_value=0, max_value=999))
    @settings(max_examples=50, deadline=None)
    def test_numeric_release_input(self, release_num: int) -> None:
        """숫자 입력도 올바르게 처리되어야 한다.
        
        Property:
            extract_release(n) == n for numeric input n > 0
        """
        parser = TDocParser()
        result = parser.extract_release(release_num)
        
        if release_num > 0:
            assert result == release_num, f"Expected {release_num}, got {result}"
        else:
            # 0 or negative: implementation may return None or 0
            # Just ensure it doesn't crash
            assert result is None or result == release_num
