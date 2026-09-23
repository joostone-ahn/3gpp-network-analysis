"""
Dashboard Components

대시보드 UI 컴포넌트들을 포함하는 서브모듈.

Components:
- filter_panel: 사이드바 필터 패널 (Task 14.2)
- network_graph: 네트워크 그래프 시각화 (Task 14.3)
- statistics_chart: 시계열 통계 라인 차트 (Task 14.4)
- centrality_table: 중심성 순위 테이블 (Task 14.4)
- community_view: 커뮤니티 목록 뷰 (Task 14.4)
- error_handler: 에러 처리 및 빈 데이터 처리 (Task 14.5)
"""

from src.dashboard.components.filter_panel import (
    FilterPanel,
    FilterSelection,
    render_filter_panel,
)

from src.dashboard.components.network_graph import (
    NetworkGraphConfig,
    NetworkGraphComponent,
    render_network_graph,
    build_network_graph,
    compute_layout,
    get_node_sizes,
    get_node_colors,
    get_edge_widths,
    create_network_figure,
    sample_large_network,
    DEFAULT_COMMUNITY_COLORS,
)

from src.dashboard.components.statistics_chart import (
    StatisticsChart,
    render_statistics_chart,
    METRIC_LABELS,
    METRIC_DESCRIPTIONS,
    METRIC_GROUPS,
)

from src.dashboard.components.centrality_table import (
    CentralityTable,
    render_centrality_table,
    CENTRALITY_LABELS,
    CENTRALITY_DESCRIPTIONS,
    CENTRALITY_METRICS,
)

from src.dashboard.components.community_view import (
    CommunityView,
    render_community_view,
)

from src.dashboard.components.error_handler import (
    ErrorType,
    ErrorContext,
    ErrorHandler,
    render_error_message,
    render_no_data_message,
    render_empty_network_message,
    render_file_error_message,
    render_pipeline_not_run_message,
    render_data_loading_spinner,
    render_data_status_banner,
    check_data_availability,
    get_error_handler,
    ERROR_MESSAGES,
)

__all__ = [
    # Filter Panel (Task 14.2)
    "FilterPanel",
    "FilterSelection",
    "render_filter_panel",
    # Network Graph (Task 14.3)
    "NetworkGraphConfig",
    "NetworkGraphComponent",
    "render_network_graph",
    "build_network_graph",
    "compute_layout",
    "get_node_sizes",
    "get_node_colors",
    "get_edge_widths",
    "create_network_figure",
    "sample_large_network",
    "DEFAULT_COMMUNITY_COLORS",
    # Statistics Chart (Task 14.4)
    "StatisticsChart",
    "render_statistics_chart",
    "METRIC_LABELS",
    "METRIC_DESCRIPTIONS",
    "METRIC_GROUPS",
    # Centrality Table (Task 14.4)
    "CentralityTable",
    "render_centrality_table",
    "CENTRALITY_LABELS",
    "CENTRALITY_DESCRIPTIONS",
    "CENTRALITY_METRICS",
    # Community View (Task 14.4)
    "CommunityView",
    "render_community_view",
    # Error Handler (Task 14.5)
    "ErrorType",
    "ErrorContext",
    "ErrorHandler",
    "render_error_message",
    "render_no_data_message",
    "render_empty_network_message",
    "render_file_error_message",
    "render_pipeline_not_run_message",
    "render_data_loading_spinner",
    "render_data_status_banner",
    "check_data_availability",
    "get_error_handler",
    "ERROR_MESSAGES",
]
