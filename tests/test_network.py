"""
Network Builder Property Tests (Property 15)

Edge 생성 정확도를 검증하는 Property-based 테스트.

테스트 대상:
- CompanyNetworkBuilder: 기업 간 협력 네트워크 Edge 생성
- WINetworkBuilder: Work Item 간 협력 네트워크 Edge 생성

Property 15 테스트 항목:
- nC2 Edge 수 검증: n개 기업이 있는 문서에서 n*(n-1)/2 개의 Edge가 생성되어야 함
- Edge 정규화 검증: 모든 Edge에서 Source < Target (알파벳 순)
- Threshold 필터링 검증: threshold 적용 후 모든 Edge의 Weight > threshold

**Validates: Requirements 17.1**
"""

from __future__ import annotations

import itertools
import math
import string
from pathlib import Path
from typing import List, Set, Tuple

import pandas as pd
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from src.network.company_network import CompanyNetworkBuilder, NetworkBuildStats
from src.network.wi_network import WINetworkBuilder, WINetworkBuildStats
from src.utils.config_loader import NetworkConfig


# =============================================================================
# Hypothesis Strategies
# =============================================================================


@st.composite
def company_names(draw: st.DrawFn) -> str:
    """유효한 기업명 생성 전략.
    
    알파벳 대문자로 시작하고, 알파벳/숫자/공백으로 구성된 2~30자 문자열.
    """
    first_char = draw(st.sampled_from(string.ascii_uppercase))
    rest_chars = draw(st.text(
        alphabet=string.ascii_letters + string.digits + " ",
        min_size=1,
        max_size=29,
    ))
    return (first_char + rest_chars).strip()


@st.composite
def work_item_codes(draw: st.DrawFn) -> str:
    """유효한 Work Item 코드 생성 전략.
    
    예: "WI_ABC", "NR_eMIMO", "Rel17_Feature"
    """
    prefix = draw(st.sampled_from(["WI", "NR", "Rel", "Feature", "Test"]))
    suffix = draw(st.text(
        alphabet=string.ascii_letters + string.digits + "_",
        min_size=1,
        max_size=20,
    ))
    return f"{prefix}_{suffix}"


@st.composite
def preprocessed_dataframe(
    draw: st.DrawFn,
    min_companies: int = 2,
    max_companies: int = 10,
    min_wis: int = 1,
    max_wis: int = 5,
    min_records: int = 5,
    max_records: int = 50,
) -> pd.DataFrame:
    """전처리된 DataFrame 생성 전략.
    
    Network Builder의 입력으로 사용될 수 있는 DataFrame을 생성한다.
    
    Args:
        min_companies: 최소 기업 수
        max_companies: 최대 기업 수
        min_wis: 최소 Work Item 수
        max_wis: 최대 Work Item 수
        min_records: 최소 레코드 수
        max_records: 최대 레코드 수
    """
    # 고유한 기업명 리스트 생성
    n_companies = draw(st.integers(min_value=min_companies, max_value=max_companies))
    companies = draw(st.lists(
        company_names(),
        min_size=n_companies,
        max_size=n_companies,
        unique=True,
    ))
    
    # 고유한 WI 코드 리스트 생성
    n_wis = draw(st.integers(min_value=min_wis, max_value=max_wis))
    wis = draw(st.lists(
        work_item_codes(),
        min_size=n_wis,
        max_size=n_wis,
        unique=True,
    ))
    
    # 레코드 생성
    n_records = draw(st.integers(min_value=min_records, max_value=max_records))
    
    records = []
    for _ in range(n_records):
        company = draw(st.sampled_from(companies))
        wi = draw(st.sampled_from(wis))
        year = draw(st.sampled_from([2022, 2023, 2024]))
        tsg = draw(st.sampled_from(["RAN", "SA", "CT"]))
        
        records.append({
            "company": company,
            "Work_Item": wi,
            "Year": year,
            "Quarter": f"{year}Q{draw(st.integers(min_value=1, max_value=4))}",
            "Release": draw(st.sampled_from([17, 18, 19])),
            "TSG": tsg,
            "WG": f"{tsg[:2]}1",  # RAN->RA1, SA->SA1 등
        })
    
    return pd.DataFrame(records)


@st.composite
def single_wi_dataframe(
    draw: st.DrawFn,
    n_companies: int = None,
) -> Tuple[pd.DataFrame, int]:
    """단일 Work Item에 여러 기업이 기고한 DataFrame 생성.
    
    nC2 Edge 수 검증에 사용된다.
    
    Returns:
        Tuple[DataFrame, 기대되는 Edge 수 (nC2)]
    """
    if n_companies is None:
        n_companies = draw(st.integers(min_value=2, max_value=10))
    
    # 고유한 기업명 생성
    companies = draw(st.lists(
        company_names(),
        min_size=n_companies,
        max_size=n_companies,
        unique=True,
    ))
    
    # 단일 Work Item
    wi = draw(work_item_codes())
    
    # 각 기업이 해당 WI에 1회 기고
    records = [
        {
            "company": company,
            "Work_Item": wi,
            "Year": 2023,
            "Quarter": "2023Q1",
            "Release": 17,
            "TSG": "RAN",
            "WG": "WG1",
        }
        for company in companies
    ]
    
    # nC2 = n*(n-1)/2
    expected_edges = n_companies * (n_companies - 1) // 2
    
    return pd.DataFrame(records), expected_edges


@st.composite
def dataframe_with_various_weights(
    draw: st.DrawFn,
    max_weight: int = 10,
) -> Tuple[pd.DataFrame, Set[Tuple[str, str]]]:
    """다양한 Weight를 가진 Edge를 생성할 DataFrame.
    
    threshold 필터링 검증에 사용된다.
    
    Returns:
        Tuple[DataFrame, 실제 기업 쌍 집합]
    """
    # 2~5개 기업
    n_companies = draw(st.integers(min_value=2, max_value=5))
    companies = draw(st.lists(
        company_names(),
        min_size=n_companies,
        max_size=n_companies,
        unique=True,
    ))
    
    # 다양한 수의 WI 생성 (Weight에 영향)
    n_wis = draw(st.integers(min_value=1, max_value=max_weight))
    wis = draw(st.lists(
        work_item_codes(),
        min_size=n_wis,
        max_size=n_wis,
        unique=True,
    ))
    
    records = []
    # 모든 기업 쌍이 최소 1개 WI에는 함께 참여하도록
    for wi in wis:
        # 이 WI에 참여할 기업들 (최소 2개)
        participating = draw(st.lists(
            st.sampled_from(companies),
            min_size=2,
            max_size=n_companies,
            unique=True,
        ))
        
        for company in participating:
            records.append({
                "company": company,
                "Work_Item": wi,
                "Year": 2023,
                "Quarter": "2023Q1",
                "Release": 17,
                "TSG": "RAN",
                "WG": "WG1",
            })
    
    # 기업 쌍 집합 생성
    company_pairs = set()
    for c1, c2 in itertools.combinations(sorted(companies), 2):
        company_pairs.add((c1, c2))
    
    return pd.DataFrame(records), company_pairs


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def test_network_config() -> NetworkConfig:
    """테스트용 Network 설정."""
    return NetworkConfig(
        thresholds=[0, 1, 2, 3, 4, 5],
        time_units=["year"],
        tsg_groups=["ALL", "RAN"],
    )


@pytest.fixture
def company_network_builder(
    test_network_config: NetworkConfig,
    tmp_path: Path,
) -> CompanyNetworkBuilder:
    """테스트용 CompanyNetworkBuilder."""
    return CompanyNetworkBuilder(
        config=test_network_config,
        output_dir=tmp_path / "processed",
    )


@pytest.fixture
def wi_network_builder(
    test_network_config: NetworkConfig,
    tmp_path: Path,
) -> WINetworkBuilder:
    """테스트용 WINetworkBuilder."""
    return WINetworkBuilder(
        config=test_network_config,
        output_dir=tmp_path / "processed",
    )


# =============================================================================
# Property 15: Edge 생성 정확도 테스트
# =============================================================================


class TestCompanyNetworkEdgeGeneration:
    """CompanyNetworkBuilder Edge 생성 Property 테스트.
    
    **Validates: Requirements 17.1**
    """
    
    @given(data=single_wi_dataframe())
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_nc2_edge_count_for_single_work_item(
        self,
        data: Tuple[pd.DataFrame, int],
    ):
        """Property 15-1: 단일 WI에서 nC2 Edge 수 검증.
        
        n개의 기업이 동일한 Work Item에 기고한 경우,
        정확히 n*(n-1)/2 개의 Edge가 생성되어야 한다.
        
        **Validates: Requirements 17.1**
        """
        df, expected_edges = data
        
        # Builder 생성 (설정 최소화)
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        # Edge 생성
        edge_df, stats = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=0,
        )
        
        # 검증: Edge 수가 nC2와 일치해야 함
        assert len(edge_df) == expected_edges, (
            f"Expected {expected_edges} edges (nC2), but got {len(edge_df)}. "
            f"Unique companies: {df['company'].nunique()}"
        )
    
    @given(df=preprocessed_dataframe())
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_edge_normalization_source_less_than_target(
        self,
        df: pd.DataFrame,
    ):
        """Property 15-2: Edge 정규화 검증 (Source < Target).
        
        모든 Edge에서 Source가 Target보다 알파벳 순으로 앞서야 한다.
        이는 (A,B)와 (B,A)를 동일한 Edge로 정규화하기 위함이다.
        
        **Validates: Requirements 17.1**
        """
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        # Edge 생성
        edge_df, _ = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=df["Year"].iloc[0] if len(df) > 0 else 2023,
            threshold=0,
        )
        
        # 빈 DataFrame이면 통과
        if len(edge_df) == 0:
            return
        
        # 검증: 모든 Edge에서 Source < Target
        invalid_edges = edge_df[edge_df["Source"] >= edge_df["Target"]]
        assert len(invalid_edges) == 0, (
            f"Found {len(invalid_edges)} edges where Source >= Target:\n"
            f"{invalid_edges[['Source', 'Target']].head()}"
        )
    
    @given(data=dataframe_with_various_weights())
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_threshold_filtering_removes_low_weight_edges(
        self,
        data: Tuple[pd.DataFrame, Set[Tuple[str, str]]],
    ):
        """Property 15-3: Threshold 필터링 검증.
        
        threshold 적용 후 모든 Edge의 Weight가 threshold보다 커야 한다.
        
        **Validates: Requirements 17.1**
        """
        df, _ = data
        
        # threshold 값 랜덤 선택
        threshold = 2
        
        config = NetworkConfig(
            thresholds=[threshold],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        # Edge 생성
        edge_df, stats = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=threshold,
        )
        
        # 빈 DataFrame이면 통과
        if len(edge_df) == 0:
            return
        
        # 검증: 모든 Edge의 Weight > threshold
        low_weight_edges = edge_df[edge_df["Weight"] <= threshold]
        assert len(low_weight_edges) == 0, (
            f"Found {len(low_weight_edges)} edges with Weight <= {threshold}:\n"
            f"{low_weight_edges[['Source', 'Target', 'Weight']].head()}"
        )
    
    @given(df=preprocessed_dataframe())
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_no_self_loops(self, df: pd.DataFrame):
        """Edge에 자기 자신과의 연결(self-loop)이 없어야 한다.
        
        **Validates: Requirements 17.1**
        """
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        # Edge 생성
        year = df["Year"].iloc[0] if len(df) > 0 else 2023
        edge_df, _ = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=year,
            threshold=0,
        )
        
        # 빈 DataFrame이면 통과
        if len(edge_df) == 0:
            return
        
        # 검증: Source != Target (self-loop 없음)
        self_loops = edge_df[edge_df["Source"] == edge_df["Target"]]
        assert len(self_loops) == 0, (
            f"Found {len(self_loops)} self-loops:\n"
            f"{self_loops[['Source', 'Target']].head()}"
        )
    
    @given(df=preprocessed_dataframe())
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_edge_weight_is_positive(self, df: pd.DataFrame):
        """모든 Edge의 Weight가 양수여야 한다.
        
        **Validates: Requirements 17.1**
        """
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        year = df["Year"].iloc[0] if len(df) > 0 else 2023
        edge_df, _ = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=year,
            threshold=0,
        )
        
        if len(edge_df) == 0:
            return
        
        # 검증: 모든 Weight > 0
        zero_or_negative = edge_df[edge_df["Weight"] <= 0]
        assert len(zero_or_negative) == 0, (
            f"Found {len(zero_or_negative)} edges with Weight <= 0:\n"
            f"{zero_or_negative.head()}"
        )
    
    @given(df=preprocessed_dataframe())
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_no_duplicate_edges(self, df: pd.DataFrame):
        """중복 Edge가 없어야 한다 ((A,B)와 (B,A)는 동일 Edge).
        
        **Validates: Requirements 17.1**
        """
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        year = df["Year"].iloc[0] if len(df) > 0 else 2023
        edge_df, _ = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=year,
            threshold=0,
        )
        
        if len(edge_df) == 0:
            return
        
        # 검증: (Source, Target) 쌍이 고유해야 함
        duplicates = edge_df.duplicated(subset=["Source", "Target"])
        assert duplicates.sum() == 0, (
            f"Found {duplicates.sum()} duplicate edges:\n"
            f"{edge_df[duplicates][['Source', 'Target']].head()}"
        )


class TestWINetworkEdgeGeneration:
    """WINetworkBuilder Edge 생성 Property 테스트.
    
    **Validates: Requirements 17.1**
    """
    
    @given(df=preprocessed_dataframe())
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_edge_normalization_source_less_than_target(
        self,
        df: pd.DataFrame,
    ):
        """Property 15-2 (WI): Edge 정규화 검증 (Source < Target).
        
        WI 네트워크에서도 모든 Edge에서 Source가 Target보다 
        알파벳 순으로 앞서야 한다.
        
        **Validates: Requirements 17.1**
        """
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = WINetworkBuilder(config=config)
        
        year = df["Year"].iloc[0] if len(df) > 0 else 2023
        edge_df, _ = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=year,
            threshold=0,
        )
        
        if len(edge_df) == 0:
            return
        
        # 검증: 모든 Edge에서 Source < Target
        invalid_edges = edge_df[edge_df["Source"] >= edge_df["Target"]]
        assert len(invalid_edges) == 0, (
            f"Found {len(invalid_edges)} WI edges where Source >= Target:\n"
            f"{invalid_edges[['Source', 'Target']].head()}"
        )
    
    @given(df=preprocessed_dataframe())
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_threshold_filtering_for_wi_network(
        self,
        df: pd.DataFrame,
    ):
        """Property 15-3 (WI): Threshold 필터링 검증.
        
        WI 네트워크에서도 threshold 적용 후 
        모든 Edge의 Weight가 threshold보다 커야 한다.
        
        **Validates: Requirements 17.1**
        """
        threshold = 2
        
        config = NetworkConfig(
            thresholds=[threshold],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = WINetworkBuilder(config=config)
        
        year = df["Year"].iloc[0] if len(df) > 0 else 2023
        edge_df, _ = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=year,
            threshold=threshold,
        )
        
        if len(edge_df) == 0:
            return
        
        # 검증: 모든 Edge의 Weight > threshold
        low_weight_edges = edge_df[edge_df["Weight"] <= threshold]
        assert len(low_weight_edges) == 0, (
            f"Found {len(low_weight_edges)} WI edges with Weight <= {threshold}:\n"
            f"{low_weight_edges[['Source', 'Target', 'Weight']].head()}"
        )
    
    @given(df=preprocessed_dataframe())
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_no_self_loops_in_wi_network(self, df: pd.DataFrame):
        """WI 네트워크에서 자기 자신과의 연결(self-loop)이 없어야 한다.
        
        **Validates: Requirements 17.1**
        """
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = WINetworkBuilder(config=config)
        
        year = df["Year"].iloc[0] if len(df) > 0 else 2023
        edge_df, _ = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=year,
            threshold=0,
        )
        
        if len(edge_df) == 0:
            return
        
        # 검증: Source != Target
        self_loops = edge_df[edge_df["Source"] == edge_df["Target"]]
        assert len(self_loops) == 0, (
            f"Found {len(self_loops)} WI self-loops:\n"
            f"{self_loops[['Source', 'Target']].head()}"
        )


class TestCompanyNetworkSpecificCases:
    """CompanyNetworkBuilder 특수 케이스 테스트.
    
    **Validates: Requirements 17.1**
    """
    
    def test_nc2_calculation_for_known_n(self):
        """알려진 n 값에 대한 nC2 계산 검증.
        
        n=5일 때 5C2 = 10개의 Edge가 생성되어야 한다.
        """
        # 5개 기업, 1개 WI
        df = pd.DataFrame({
            "company": ["A", "B", "C", "D", "E"],
            "Work_Item": ["WI_1"] * 5,
            "Year": [2023] * 5,
            "Quarter": ["2023Q1"] * 5,
            "Release": [17] * 5,
            "TSG": ["RAN"] * 5,
            "WG": ["WG1"] * 5,
        })
        
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        edge_df, stats = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=0,
        )
        
        # 5C2 = 10
        expected_edges = 5 * 4 // 2
        assert len(edge_df) == expected_edges
    
    def test_threshold_zero_keeps_all_edges(self):
        """threshold=0일 때 모든 Edge가 유지되어야 한다."""
        df = pd.DataFrame({
            "company": ["A", "B", "C"],
            "Work_Item": ["WI_1", "WI_1", "WI_1"],
            "Year": [2023, 2023, 2023],
            "Quarter": ["2023Q1"] * 3,
            "Release": [17] * 3,
            "TSG": ["RAN"] * 3,
            "WG": ["WG1"] * 3,
        })
        
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        edge_df_0, stats_0 = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=0,
        )
        
        # 3C2 = 3, 모두 Weight=1
        assert len(edge_df_0) == 3
        assert stats_0.edges_before_threshold == stats_0.edges_after_threshold
    
    def test_threshold_removes_appropriate_edges(self):
        """threshold 값에 따라 적절한 Edge가 제거되어야 한다."""
        # A-B: WI_1, WI_2에 공동 참여 (Weight=2)
        # A-C: WI_1에만 공동 참여 (Weight=1)
        # B-C: WI_1에만 공동 참여 (Weight=1)
        df = pd.DataFrame({
            "company": ["A", "B", "C", "A", "B"],
            "Work_Item": ["WI_1", "WI_1", "WI_1", "WI_2", "WI_2"],
            "Year": [2023] * 5,
            "Quarter": ["2023Q1"] * 5,
            "Release": [17] * 5,
            "TSG": ["RAN"] * 5,
            "WG": ["WG1"] * 5,
        })
        
        config = NetworkConfig(
            thresholds=[1],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        # threshold=0: 모든 Edge 유지
        edge_df_0, stats_0 = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=0,
        )
        assert len(edge_df_0) == 3  # A-B, A-C, B-C
        
        # threshold=1: Weight > 1인 Edge만 유지
        edge_df_1, stats_1 = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=1,
        )
        assert len(edge_df_1) == 1  # A-B만 (Weight=2)
        assert edge_df_1.iloc[0]["Weight"] == 2
    
    def test_edge_normalization_alphabetical_order(self):
        """Edge 정규화: Source < Target 알파벳 순 검증."""
        df = pd.DataFrame({
            "company": ["Zebra", "Apple", "Banana"],
            "Work_Item": ["WI_1"] * 3,
            "Year": [2023] * 3,
            "Quarter": ["2023Q1"] * 3,
            "Release": [17] * 3,
            "TSG": ["RAN"] * 3,
            "WG": ["WG1"] * 3,
        })
        
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        edge_df, _ = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=0,
        )
        
        # 모든 Edge에서 Source < Target (알파벳 순)
        for _, row in edge_df.iterrows():
            assert row["Source"] < row["Target"], (
                f"Edge not normalized: {row['Source']} should be < {row['Target']}"
            )
        
        # 기대하는 Edge: Apple-Banana, Apple-Zebra, Banana-Zebra
        expected_edges = {("Apple", "Banana"), ("Apple", "Zebra"), ("Banana", "Zebra")}
        actual_edges = {(row["Source"], row["Target"]) for _, row in edge_df.iterrows()}
        assert actual_edges == expected_edges


class TestWINetworkSpecificCases:
    """WINetworkBuilder 특수 케이스 테스트.
    
    **Validates: Requirements 17.1**
    """
    
    def test_wi_nc2_for_single_company(self):
        """단일 기업이 여러 WI에 기고한 경우 WI 쌍 검증.
        
        1개 기업이 3개 WI에 기고하면 3C2 = 3개 Edge가 생성되어야 한다.
        """
        df = pd.DataFrame({
            "company": ["CompanyA"] * 3,
            "Work_Item": ["WI_1", "WI_2", "WI_3"],
            "Year": [2023] * 3,
            "Quarter": ["2023Q1"] * 3,
            "Release": [17] * 3,
            "TSG": ["RAN"] * 3,
            "WG": ["WG1"] * 3,
        })
        
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = WINetworkBuilder(config=config)
        
        edge_df, stats = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=0,
        )
        
        # 3C2 = 3
        assert len(edge_df) == 3
    
    def test_wi_weight_is_company_count(self):
        """WI Edge Weight는 동시에 기고한 고유 기업 수여야 한다.
        
        2개 기업이 같은 2개 WI에 기고하면 
        WI 쌍의 Weight = 2 (두 기업 모두 해당 WI 쌍에 기고)
        """
        df = pd.DataFrame({
            "company": ["A", "A", "B", "B"],
            "Work_Item": ["WI_1", "WI_2", "WI_1", "WI_2"],
            "Year": [2023] * 4,
            "Quarter": ["2023Q1"] * 4,
            "Release": [17] * 4,
            "TSG": ["RAN"] * 4,
            "WG": ["WG1"] * 4,
        })
        
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = WINetworkBuilder(config=config)
        
        edge_df, _ = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=0,
        )
        
        # WI_1-WI_2 Edge의 Weight = 2 (A와 B 모두 두 WI에 기고)
        assert len(edge_df) == 1
        assert edge_df.iloc[0]["Weight"] == 2


class TestEdgeCasesAndEmptyInputs:
    """경계 케이스 및 빈 입력 테스트.
    
    **Validates: Requirements 17.1**
    """
    
    def test_empty_dataframe_returns_empty_edges(self):
        """빈 DataFrame 입력 시 빈 Edge DataFrame 반환."""
        df = pd.DataFrame(columns=[
            "company", "Work_Item", "Year", "Quarter", "Release", "TSG", "WG"
        ])
        
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        edge_df, stats = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=0,
        )
        
        assert len(edge_df) == 0
        assert stats.edges_after_threshold == 0
    
    def test_single_company_produces_no_edges(self):
        """단일 기업만 있으면 Edge가 생성되지 않아야 한다."""
        df = pd.DataFrame({
            "company": ["OnlyCompany"] * 3,
            "Work_Item": ["WI_1", "WI_2", "WI_3"],
            "Year": [2023] * 3,
            "Quarter": ["2023Q1"] * 3,
            "Release": [17] * 3,
            "TSG": ["RAN"] * 3,
            "WG": ["WG1"] * 3,
        })
        
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        edge_df, _ = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=0,
        )
        
        # 기업이 1개이므로 기업 간 Edge 없음
        assert len(edge_df) == 0
    
    def test_two_companies_one_wi_produces_one_edge(self):
        """2개 기업, 1개 WI에서 정확히 1개 Edge 생성."""
        df = pd.DataFrame({
            "company": ["Alpha", "Beta"],
            "Work_Item": ["WI_1", "WI_1"],
            "Year": [2023, 2023],
            "Quarter": ["2023Q1", "2023Q1"],
            "Release": [17, 17],
            "TSG": ["RAN", "RAN"],
            "WG": ["WG1", "WG1"],
        })
        
        config = NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"],
        )
        builder = CompanyNetworkBuilder(config=config)
        
        edge_df, _ = builder.build_edges(
            df=df,
            tsg_group="ALL",
            time_unit="year",
            time_value=2023,
            threshold=0,
        )
        
        # 2C2 = 1
        assert len(edge_df) == 1
        assert edge_df.iloc[0]["Source"] == "Alpha"
        assert edge_df.iloc[0]["Target"] == "Beta"
        assert edge_df.iloc[0]["Weight"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
