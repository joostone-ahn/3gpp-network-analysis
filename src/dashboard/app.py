"""
Streamlit Dashboard Application (Stage 8)

3GPP 네트워크 분석 결과를 시각화하는 인터랙티브 대시보드.

실행 방법:
    streamlit run src/dashboard/app.py

요구사항:
- 13.1: 사이드바 필터 패널 제공 (Task 14.2)
- 13.2: 인터랙티브 네트워크 그래프 표시 (Task 14.3)
- 13.3: 시계열 통계 차트 표시 (Task 14.4)
- 13.4: Centrality 순위 테이블 및 검색 (Task 14.4)
- 13.5: 커뮤니티 목록 및 주요 노드 표시 (Task 14.4)
- 13.6: 데이터 없음 메시지 처리 (Task 14.5)
- 13.7: streamlit run src/dashboard/app.py 명령으로 실행
- 16.3: 5초 이내 그래프 로딩 (사전 계산된 Parquet 로드)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import streamlit as st

# 데이터 로더 임포트
from src.dashboard.data_loader import (
    DashboardDataLoader,
    EdgeListData,
    CentralityData,
    CommunityData,
    StatisticsData,
    get_data_loader,
)

# 필터 패널 컴포넌트 임포트
from src.dashboard.components import (
    FilterSelection,
    render_network_graph,
    render_statistics_chart,
    render_centrality_table,
    render_community_view,
    # 에러 핸들러 (Task 14.5)
    render_no_data_message,
    render_empty_network_message,
    render_pipeline_not_run_message,
    render_data_status_banner,
    render_data_loading_spinner,
    check_data_availability,
    get_error_handler,
    ErrorType,
)

# Streamlit 페이지 설정
st.set_page_config(
    page_title="3GPP Network Analysis Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


class DashboardApp:
    """Streamlit 기반 인터랙티브 대시보드 애플리케이션.
    
    분석 결과를 다양한 조건으로 탐색할 수 있는 대시보드를 제공한다.
    
    Attributes:
        data_loader: 데이터 로더 인스턴스
    
    Usage:
        >>> app = DashboardApp()
        >>> app.run()
    """
    
    def __init__(self, data_loader: Optional[DashboardDataLoader] = None):
        """DashboardApp 초기화.
        
        Args:
            data_loader: 데이터 로더. None이면 기본 로더 사용.
        """
        self.data_loader = data_loader or get_data_loader()
    
    def run(self) -> None:
        """대시보드 애플리케이션 실행."""
        # 헤더
        st.title("📊 3GPP Network Analysis Dashboard")
        st.markdown("---")
        
        # 데이터 상태 확인 (Task 14.5: 데이터 없으면 안내 메시지)
        if not render_data_status_banner():
            # 데이터가 전혀 없는 경우 여기서 종료
            return
        
        # 사이드바 필터 렌더링
        filter_selection = self._render_sidebar()
        
        if filter_selection is None:
            st.info("👈 사이드바에서 분석 조건을 선택하세요.")
            return
        
        # 데이터 로드 (with spinner)
        with render_data_loading_spinner("분석 데이터를 로드하는 중..."):
            data = self._load_data(filter_selection)
        
        # 메인 컨텐츠 영역
        self._render_main_content(filter_selection, data)
    
    def _render_sidebar(self) -> Optional[FilterSelection]:
        """사이드바 필터 패널 렌더링.
        
        Returns:
            FilterSelection 또는 None (필수 값이 선택되지 않은 경우)
        """
        st.sidebar.header("🔍 필터 설정")
        
        # 네트워크 유형 선택
        network_types = self.data_loader.get_available_network_types()
        network_type = st.sidebar.selectbox(
            "네트워크 유형",
            options=network_types,
            index=0,
            format_func=lambda x: "기업 간 네트워크" if x == "company" else "Work Item 간 네트워크",
        )
        
        # TSG 그룹 선택
        tsg_groups = self.data_loader.get_available_tsg_groups()
        tsg_group = st.sidebar.selectbox(
            "TSG 그룹",
            options=tsg_groups,
            index=0,
        )
        
        # 시간 단위 선택
        time_units = self.data_loader.get_available_time_units()
        time_unit_labels = {
            "year": "연도별",
            "release": "Release별",
            "quarter": "분기별",
        }
        time_unit = st.sidebar.selectbox(
            "시간 단위",
            options=time_units,
            index=0,
            format_func=lambda x: time_unit_labels.get(x, x),
        )
        
        # 시간 값 선택 (사용 가능한 값 조회)
        time_values = self.data_loader.get_available_time_values(
            time_unit=time_unit,
            tsg_group=tsg_group,
            network_type=network_type,
        )
        
        if not time_values:
            st.sidebar.warning(
                f"⚠️ 선택한 조건에 해당하는 데이터가 없습니다.\n\n"
                f"**💡 해결 방법:**\n"
                f"- 다른 조건을 선택해 보세요.\n"
                f"- 분석 파이프라인을 실행해 주세요."
            )
            return None
        
        time_value = st.sidebar.selectbox(
            "시간 값",
            options=time_values,
            index=len(time_values) - 1 if time_values else 0,  # 가장 최근 값 기본 선택
        )
        
        # Threshold 선택
        thresholds = self.data_loader.get_available_thresholds()
        threshold = st.sidebar.slider(
            "Edge Weight 임계값",
            min_value=min(thresholds) if thresholds else 0,
            max_value=max(thresholds) if thresholds else 9,
            value=0,
            step=1,
            help="임계값 이하의 Edge는 제외됩니다. 값을 높이면 더 강한 협력 관계만 표시됩니다.",
        )
        
        # 구분선
        st.sidebar.markdown("---")
        
        # 데이터 요약 정보
        st.sidebar.subheader("📈 데이터 정보")
        summary = self.data_loader.get_data_summary()
        st.sidebar.text(f"Edge list 파일: {summary['processed_files']}개")
        st.sidebar.text(f"분석 결과 파일: {summary['results_files']}개")
        
        # 데이터 없음 경고
        if summary['processed_files'] == 0:
            st.sidebar.error("⚠️ Edge list 파일이 없습니다.")
        elif summary['results_files'] == 0:
            st.sidebar.warning("⚠️ 분석 결과 파일이 없습니다.")
        
        return FilterSelection(
            tsg_group=tsg_group,
            time_unit=time_unit,
            time_value=time_value,
            time_range=None,
            threshold=threshold,
            network_type=network_type,
        )
    
    def _load_data(self, selection: FilterSelection) -> Dict[str, Any]:
        """선택된 조건에 대한 데이터 로드.
        
        Args:
            selection: 필터 선택 값
            
        Returns:
            로드된 데이터 딕셔너리
        """
        return self.data_loader.load_all_for_selection(selection)
    
    def _render_main_content(
        self,
        selection: FilterSelection,
        data: Dict[str, Any],
    ) -> None:
        """메인 컨텐츠 영역 렌더링.
        
        Args:
            selection: 필터 선택 값
            data: 로드된 데이터
        """
        # 현재 선택 조건 표시
        st.subheader("📋 선택된 조건")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        network_type_label = "기업 간 네트워크" if selection.network_type == "company" else "WI 간 네트워크"
        col1.metric("네트워크 유형", network_type_label)
        col2.metric("TSG 그룹", selection.tsg_group)
        col3.metric("시간 단위", selection.time_unit)
        col4.metric("시간 값", str(selection.time_value))
        col5.metric("Threshold", selection.threshold)
        
        st.markdown("---")
        
        # Edge list 데이터 확인
        edge_data: Optional[EdgeListData] = data.get("edge_list")
        centrality_data: Optional[CentralityData] = data.get("centrality")
        community_data: Optional[CommunityData] = data.get("community")
        
        # 데이터 없음 처리 (Task 14.5)
        if edge_data is None:
            self._render_no_data_message(selection)
            return
        
        # 빈 네트워크 처리 (Task 14.5)
        if edge_data.df.empty or edge_data.node_count == 0:
            render_empty_network_message(
                node_count=edge_data.node_count,
                edge_count=edge_data.edge_count,
                threshold=selection.threshold,
            )
            return
        
        # 기본 통계 표시
        st.subheader("📊 네트워크 개요")
        stat_col1, stat_col2, stat_col3 = st.columns(3)
        stat_col1.metric("노드 수", f"{edge_data.node_count:,}")
        stat_col2.metric("Edge 수", f"{edge_data.edge_count:,}")
        stat_col3.metric("총 Weight", f"{edge_data.total_weight:,}")
        
        st.markdown("---")
        
        # 탭 구성 (시각화 컴포넌트는 후속 태스크에서 구현)
        tab1, tab2, tab3, tab4 = st.tabs([
            "🕸️ 네트워크 그래프",
            "📈 통계 차트",
            "🏆 중심성 순위",
            "👥 커뮤니티",
        ])
        
        with tab1:
            self._render_network_graph_placeholder(edge_data, community_data, centrality_data)
        
        with tab2:
            self._render_statistics_placeholder(selection)
        
        with tab3:
            self._render_centrality_placeholder(centrality_data, selection)
        
        with tab4:
            self._render_community_placeholder(community_data, selection)
    
    def _render_no_data_message(self, selection: FilterSelection) -> None:
        """데이터 없음 메시지 표시 (Task 14.5 개선).
        
        Args:
            selection: 필터 선택 값
        """
        # 향상된 에러 핸들러 사용
        render_no_data_message(
            tsg_group=selection.tsg_group,
            time_unit=selection.time_unit,
            time_value=selection.time_value,
            threshold=selection.threshold,
            network_type=selection.network_type,
            data_type="Edge list 데이터",
            custom_suggestions=[
                "다른 TSG 그룹을 선택해 보세요.",
                "시간 단위 또는 시간 값을 변경해 보세요.",
            ],
        )
    
    def _render_network_graph_placeholder(
        self,
        edge_data: EdgeListData,
        community_data: Optional[CommunityData],
        centrality_data: Optional[CentralityData] = None,
    ) -> None:
        """네트워크 그래프 렌더링 (Task 14.3 구현).
        
        사전 계산된 분석 결과(Parquet)를 로드하여 5초 이내 로딩을 보장합니다.
        
        Args:
            edge_data: Edge list 데이터
            community_data: 커뮤니티 데이터 (노드 색상용)
            centrality_data: 중심성 데이터 (hover 정보용)
        """
        # Plotly 네트워크 그래프 렌더링
        render_network_graph(
            edge_data=edge_data,
            community_data=community_data,
            centrality_data=centrality_data,
            title=None,  # 자동 생성
            height=700,
            show_controls=True,
        )
        
        # Edge list 미리보기
        with st.expander("📋 Edge List 미리보기"):
            st.dataframe(
                edge_data.df.head(100),
                use_container_width=True,
                height=400,
            )
    
    def _render_statistics_placeholder(self, selection: FilterSelection) -> None:
        """통계 차트 렌더링 (Task 14.4 구현).
        
        시계열 통계 라인 차트를 표시합니다.
        노드 수, Edge 수, 밀도 등 네트워크 지표의 시간에 따른 변화를 시각화합니다.
        
        Args:
            selection: 필터 선택 값
        """
        render_statistics_chart(selection, self.data_loader)
    
    def _render_centrality_placeholder(
        self,
        centrality_data: Optional[CentralityData],
        selection: FilterSelection,
    ) -> None:
        """중심성 순위 테이블 렌더링 (Task 14.4 구현).
        
        Degree, Betweenness, Closeness, Eigenvector Centrality를 표시하고
        노드 검색 기능을 제공합니다.
        
        Args:
            centrality_data: 중심성 데이터
            selection: 필터 선택 값
        """
        render_centrality_table(selection, self.data_loader)
    
    def _render_community_placeholder(
        self,
        community_data: Optional[CommunityData],
        selection: FilterSelection,
    ) -> None:
        """커뮤니티 목록 뷰 렌더링 (Task 14.4 구현).
        
        커뮤니티 크기, 주요 노드, 구성원 목록 등을 표시합니다.
        
        Args:
            community_data: 커뮤니티 데이터
            selection: 필터 선택 값
        """
        render_community_view(selection, self.data_loader)


def main():
    """대시보드 메인 함수."""
    app = DashboardApp()
    app.run()


if __name__ == "__main__":
    main()
