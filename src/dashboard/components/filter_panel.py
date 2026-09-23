"""
Sidebar Filter Panel Component

사이드바 필터 패널을 제공하는 컴포넌트.
TSG 그룹, 시간 단위, 시간 범위, threshold, 네트워크 유형 선택 필터 제공.

Requirements: 13.1
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union
import streamlit as st
import pandas as pd

from src.utils.config_loader import load_config, NetworkConfig


@dataclass
class FilterSelection:
    """필터 선택 결과를 담는 데이터클래스.
    
    Attributes:
        tsg_group: TSG 그룹 ('ALL', 'RAN', 'SA', 'CT')
        time_unit: 시간 단위 ('year', 'release', 'quarter')
        time_value: 선택된 시간 값 (예: 2023, 17, '2023Q1')
        time_range: 시간 범위 (시작값, 종료값 튜플) - 범위 선택 시
        threshold: Weight 임계값 (0-9)
        network_type: 네트워크 유형 ('company', 'wi')
    """
    tsg_group: str
    time_unit: str
    time_value: Optional[Union[int, str]]
    time_range: Optional[Tuple[Union[int, str], Union[int, str]]]
    threshold: int
    network_type: str


class FilterPanel:
    """사이드바 필터 패널 컴포넌트.
    
    Streamlit 사이드바에 다양한 필터 옵션을 제공하여
    대시보드의 데이터 조회 조건을 설정할 수 있게 합니다.
    
    Attributes:
        config: NetworkConfig 설정 객체
        tsg_groups: 사용 가능한 TSG 그룹 목록
        time_units: 사용 가능한 시간 단위 목록
        thresholds: 사용 가능한 threshold 목록
    """
    
    # 시간 단위 라벨 매핑 (한국어)
    TIME_UNIT_LABELS = {
        "year": "연도 (Year)",
        "release": "릴리즈 (Release)",
        "quarter": "분기 (Quarter)"
    }
    
    # 네트워크 유형 라벨 매핑 (한국어)
    NETWORK_TYPE_LABELS = {
        "company": "기업 협력 네트워크 (Company Network)",
        "wi": "Work Item 네트워크 (WI Network)"
    }
    
    def __init__(
        self,
        config: Optional[NetworkConfig] = None,
        processed_dir: Optional[Path] = None,
        results_dir: Optional[Path] = None,
    ):
        """FilterPanel 초기화.
        
        Args:
            config: NetworkConfig 설정 객체. None이면 config 파일에서 로드.
            processed_dir: Edge list 저장 디렉토리. None이면 기본 경로 사용.
            results_dir: 분석 결과 저장 디렉토리. None이면 기본 경로 사용.
        """
        if config is None:
            self.config = load_config("network")
        else:
            self.config = config
        
        self.tsg_groups = self.config.tsg_groups
        self.time_units = self.config.time_units
        self.thresholds = self.config.thresholds
        
        # 데이터 디렉토리 설정
        self.processed_dir = processed_dir or Path("data/processed")
        self.results_dir = results_dir or Path("data/results")
        
        # 사용 가능한 시간 값 캐시
        self._available_time_values: dict = {}
    
    def _get_available_time_values(
        self,
        time_unit: str,
        tsg_group: str = "ALL",
        network_type: str = "company"
    ) -> List[Union[int, str]]:
        """지정된 조건에서 사용 가능한 시간 값 목록을 조회.
        
        processed 디렉토리에서 실제 파일이 존재하는 시간 값만 반환합니다.
        
        Args:
            time_unit: 시간 단위 ('year', 'release', 'quarter')
            tsg_group: TSG 그룹
            network_type: 네트워크 유형
            
        Returns:
            사용 가능한 시간 값 목록 (정렬됨)
        """
        cache_key = f"{network_type}_{tsg_group}_{time_unit}"
        
        if cache_key in self._available_time_values:
            return self._available_time_values[cache_key]
        
        time_values = set()
        
        # 파일명 패턴: {network_type}_{tsg}_{time_unit}_{time_value}_{threshold}.parquet
        prefix = f"{network_type}_{tsg_group}_{time_unit}_"
        
        if self.processed_dir.exists():
            for filepath in self.processed_dir.glob(f"{prefix}*.parquet"):
                filename = filepath.stem
                # 파일명에서 time_value 추출
                parts = filename.replace(prefix, "").rsplit("_", 1)
                if len(parts) >= 1:
                    time_value_str = parts[0]
                    try:
                        if time_unit in ["year", "release"]:
                            time_values.add(int(time_value_str))
                        else:
                            # quarter는 '2023Q1' 형식
                            time_values.add(time_value_str)
                    except ValueError:
                        # quarter 형식일 수 있음
                        time_values.add(time_value_str)
        
        # 정렬 (연도/릴리즈는 내림차순, 분기는 알파벳 내림차순)
        if time_unit in ["year", "release"]:
            sorted_values = sorted(time_values, reverse=True)
        else:
            sorted_values = sorted(time_values, reverse=True)
        
        self._available_time_values[cache_key] = sorted_values
        return sorted_values
    
    def _get_default_time_values(self, time_unit: str) -> List[Union[int, str]]:
        """시간 단위별 기본 시간 값 목록 반환.
        
        실제 데이터가 없을 때 사용할 기본값을 제공합니다.
        
        Args:
            time_unit: 시간 단위
            
        Returns:
            기본 시간 값 목록
        """
        if time_unit == "year":
            return list(range(2023, 2015, -1))  # 2023, 2022, ..., 2016
        elif time_unit == "release":
            return list(range(18, 14, -1))  # 18, 17, 16, 15
        else:  # quarter
            quarters = []
            for year in range(2023, 2015, -1):
                for q in range(4, 0, -1):
                    quarters.append(f"{year}Q{q}")
            return quarters
    
    def render(self, use_range: bool = False) -> FilterSelection:
        """사이드바 필터 패널을 렌더링하고 선택 결과를 반환.
        
        Args:
            use_range: True면 시간 범위 선택, False면 단일 시간 값 선택
            
        Returns:
            FilterSelection 객체
        """
        st.sidebar.header("🔍 필터 설정")
        
        # 구분선
        st.sidebar.markdown("---")
        
        # 1. 네트워크 유형 선택
        st.sidebar.subheader("📊 네트워크 유형")
        network_type_options = list(self.NETWORK_TYPE_LABELS.keys())
        network_type_labels = list(self.NETWORK_TYPE_LABELS.values())
        
        network_type_idx = st.sidebar.selectbox(
            "분석할 네트워크 유형을 선택하세요",
            range(len(network_type_options)),
            format_func=lambda x: network_type_labels[x],
            key="filter_network_type"
        )
        network_type = network_type_options[network_type_idx]
        
        st.sidebar.markdown("---")
        
        # 2. TSG 그룹 선택
        st.sidebar.subheader("🏢 TSG 그룹")
        tsg_group = st.sidebar.selectbox(
            "TSG 그룹을 선택하세요",
            self.tsg_groups,
            index=0,
            key="filter_tsg_group",
            help="ALL: 전체, RAN: 무선 접속, SA: 서비스 및 시스템, CT: 핵심망"
        )
        
        st.sidebar.markdown("---")
        
        # 3. 시간 단위 선택
        st.sidebar.subheader("📅 시간 단위")
        time_unit_options = self.time_units
        time_unit_labels = [self.TIME_UNIT_LABELS.get(t, t) for t in time_unit_options]
        
        time_unit_idx = st.sidebar.selectbox(
            "시간 단위를 선택하세요",
            range(len(time_unit_options)),
            format_func=lambda x: time_unit_labels[x],
            key="filter_time_unit"
        )
        time_unit = time_unit_options[time_unit_idx]
        
        # 4. 시간 값/범위 선택
        # 사용 가능한 시간 값 조회
        available_values = self._get_available_time_values(
            time_unit, tsg_group, network_type
        )
        
        # 실제 데이터가 없으면 기본값 사용
        if not available_values:
            available_values = self._get_default_time_values(time_unit)
        
        time_value = None
        time_range = None
        
        if use_range and len(available_values) >= 2:
            # 범위 선택 모드
            st.sidebar.subheader("📆 시간 범위")
            
            if time_unit in ["year", "release"]:
                # 숫자형 범위
                min_val = min(available_values)
                max_val = max(available_values)
                time_range = st.sidebar.slider(
                    f"{self.TIME_UNIT_LABELS.get(time_unit, time_unit)} 범위",
                    min_value=min_val,
                    max_value=max_val,
                    value=(min_val, max_val),
                    key="filter_time_range"
                )
            else:
                # 분기는 select_slider 사용
                sorted_quarters = sorted(available_values)
                start_idx, end_idx = st.sidebar.select_slider(
                    f"{self.TIME_UNIT_LABELS.get(time_unit, time_unit)} 범위",
                    options=range(len(sorted_quarters)),
                    value=(0, len(sorted_quarters) - 1),
                    format_func=lambda x: sorted_quarters[x],
                    key="filter_time_range_quarter"
                )
                time_range = (sorted_quarters[start_idx], sorted_quarters[end_idx])
        else:
            # 단일 값 선택 모드
            st.sidebar.subheader("📆 시간 선택")
            
            if available_values:
                if time_unit in ["year", "release"]:
                    time_value = st.sidebar.selectbox(
                        f"{self.TIME_UNIT_LABELS.get(time_unit, time_unit)}를 선택하세요",
                        available_values,
                        key="filter_time_value"
                    )
                else:
                    time_value = st.sidebar.selectbox(
                        f"{self.TIME_UNIT_LABELS.get(time_unit, time_unit)}를 선택하세요",
                        available_values,
                        key="filter_time_value_quarter"
                    )
            else:
                st.sidebar.warning("사용 가능한 데이터가 없습니다.")
        
        st.sidebar.markdown("---")
        
        # 5. Threshold 선택
        st.sidebar.subheader("⚖️ Weight Threshold")
        threshold = st.sidebar.slider(
            "Edge Weight 최소값",
            min_value=min(self.thresholds),
            max_value=max(self.thresholds),
            value=0,
            step=1,
            key="filter_threshold",
            help="설정된 값 이하의 Weight를 가진 Edge는 제외됩니다."
        )
        
        st.sidebar.markdown("---")
        
        # 현재 선택 요약 표시
        st.sidebar.subheader("📋 선택 요약")
        summary_col1, summary_col2 = st.sidebar.columns(2)
        
        with summary_col1:
            st.markdown(f"**TSG:** {tsg_group}")
            st.markdown(f"**유형:** {network_type}")
        
        with summary_col2:
            st.markdown(f"**시간:** {time_value or time_range}")
            st.markdown(f"**Threshold:** ≥ {threshold}")
        
        return FilterSelection(
            tsg_group=tsg_group,
            time_unit=time_unit,
            time_value=time_value,
            time_range=time_range,
            threshold=threshold,
            network_type=network_type
        )
    
    def render_compact(self) -> FilterSelection:
        """컴팩트 형태의 필터 패널 렌더링.
        
        사이드바 공간이 제한적일 때 사용합니다.
        
        Returns:
            FilterSelection 객체
        """
        st.sidebar.header("🔍 필터")
        
        # 네트워크 유형과 TSG 그룹을 같은 줄에
        col1, col2 = st.sidebar.columns(2)
        
        with col1:
            network_type = st.selectbox(
                "네트워크",
                ["company", "wi"],
                format_func=lambda x: "기업" if x == "company" else "WI",
                key="compact_network_type"
            )
        
        with col2:
            tsg_group = st.selectbox(
                "TSG",
                self.tsg_groups,
                key="compact_tsg_group"
            )
        
        # 시간 단위와 값
        col3, col4 = st.sidebar.columns(2)
        
        with col3:
            time_unit = st.selectbox(
                "시간 단위",
                self.time_units,
                format_func=lambda x: {"year": "연도", "release": "릴리즈", "quarter": "분기"}.get(x, x),
                key="compact_time_unit"
            )
        
        with col4:
            available_values = self._get_available_time_values(
                time_unit, tsg_group, network_type
            )
            if not available_values:
                available_values = self._get_default_time_values(time_unit)
            
            time_value = st.selectbox(
                "시간 값",
                available_values if available_values else [None],
                key="compact_time_value"
            )
        
        # Threshold
        threshold = st.sidebar.slider(
            "Threshold",
            0, 9, 0,
            key="compact_threshold"
        )
        
        return FilterSelection(
            tsg_group=tsg_group,
            time_unit=time_unit,
            time_value=time_value,
            time_range=None,
            threshold=threshold,
            network_type=network_type
        )
    
    def clear_cache(self):
        """시간 값 캐시를 초기화."""
        self._available_time_values.clear()


def render_filter_panel(
    config: Optional[NetworkConfig] = None,
    processed_dir: Optional[Path] = None,
    use_range: bool = False,
    compact: bool = False
) -> FilterSelection:
    """필터 패널을 렌더링하는 헬퍼 함수.
    
    Args:
        config: NetworkConfig 설정 객체
        processed_dir: Edge list 저장 디렉토리
        use_range: 시간 범위 선택 사용 여부
        compact: 컴팩트 모드 사용 여부
        
    Returns:
        FilterSelection 객체
    """
    panel = FilterPanel(config=config, processed_dir=processed_dir)
    
    if compact:
        return panel.render_compact()
    else:
        return panel.render(use_range=use_range)
