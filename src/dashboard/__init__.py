"""
Dashboard Module (Stage 8)

Streamlit 기반 인터랙티브 대시보드를 제공하는 모듈.

요구사항:
- 13.1: 사이드바 필터 패널 제공
- 13.2: 인터랙티브 네트워크 그래프 표시
- 13.3: 시계열 통계 차트 표시
- 13.4: Centrality 순위 테이블 및 검색
- 13.5: 커뮤니티 목록 및 주요 노드 표시
- 13.6: 데이터 없음 메시지 처리
- 13.7: streamlit run src/dashboard/app.py 명령으로 실행

Usage:
    # 데이터 로드
    from src.dashboard import DashboardDataLoader, FilterSelection
    
    loader = DashboardDataLoader()
    selection = FilterSelection(
        tsg_group="RAN",
        time_unit="year",
        time_value=2023,
        time_range=None,
        threshold=0,
        network_type="company"
    )
    edge_data = loader.load_edge_list_from_selection(selection)
    
    # 또는 파라미터 직접 사용
    edge_data = loader.load_edge_list(
        tsg_group="RAN",
        time_unit="year",
        time_value=2023,
        threshold=0,
        network_type="company"
    )
    
    # 대시보드 실행 (터미널에서)
    # streamlit run src/dashboard/app.py

Components:
    - FilterPanel: 사이드바 필터 패널 컴포넌트
    - FilterSelection: 필터 선택 결과 데이터클래스
    - DashboardDataLoader: 분석 결과 데이터 로더
"""

# 필터 패널 컴포넌트
from src.dashboard.components import (
    FilterPanel,
    FilterSelection,
    render_filter_panel,
)

# 데이터 로더
from src.dashboard.data_loader import (
    DashboardDataLoader,
    EdgeListData,
    CentralityData,
    CommunityData,
    StatisticsData,
    get_data_loader,
)

__all__ = [
    # Filter Panel Component
    "FilterPanel",
    "FilterSelection",
    "render_filter_panel",
    # Data Loader
    "DashboardDataLoader",
    "get_data_loader",
    # Data Container Classes
    "EdgeListData",
    "CentralityData",
    "CommunityData",
    "StatisticsData",
]
