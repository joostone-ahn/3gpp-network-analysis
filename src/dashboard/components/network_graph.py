"""
Network Graph Visualization Component (Task 14.3)

Plotly를 사용한 인터랙티브 네트워크 그래프 시각화 컴포넌트.

Requirements:
- 13.2: 인터랙티브 네트워크 그래프 표시
  - 노드 크기: Degree에 비례
  - 노드 색상: 커뮤니티 구분
  - Edge 굵기: Weight에 비례
- 16.3: 사전 계산된 분석 결과(Parquet)를 로드하여 5초 이내 로딩 보장

Implementation Notes:
- 사전 계산된 위치(positions)가 있으면 사용, 없으면 Fruchterman-Reingold 레이아웃 계산
- 노드 hover 시 상세 정보 표시
- Edge hover 시 Weight 및 연결된 노드 표시
- 큰 네트워크의 경우 샘플링 옵션 제공
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.data_loader import EdgeListData, CommunityData, CentralityData
from src.utils.logger import get_logger

# 모듈 로거
logger = get_logger("dashboard", default_stage="network_graph")

# 기본 색상 팔레트 (커뮤니티 구분용)
DEFAULT_COMMUNITY_COLORS = [
    '#1f77b4',  # Blue
    '#ff7f0e',  # Orange
    '#2ca02c',  # Green
    '#d62728',  # Red
    '#9467bd',  # Purple
    '#8c564b',  # Brown
    '#e377c2',  # Pink
    '#7f7f7f',  # Gray
    '#bcbd22',  # Olive
    '#17becf',  # Cyan
    '#aec7e8',  # Light Blue
    '#ffbb78',  # Light Orange
    '#98df8a',  # Light Green
    '#ff9896',  # Light Red
    '#c5b0d5',  # Light Purple
]

# 기본 레이아웃 설정
DEFAULT_LAYOUT_CONFIG = {
    'seed': 42,  # 재현성을 위한 seed 고정
    'k': None,  # 노드 간 최적 거리 (None이면 자동 계산)
    'iterations': 50,  # 반복 횟수
}

# 노드 크기 범위
NODE_SIZE_MIN = 8
NODE_SIZE_MAX = 50

# Edge 굵기 범위
EDGE_WIDTH_MIN = 0.5
EDGE_WIDTH_MAX = 5.0


@dataclass
class NetworkGraphConfig:
    """네트워크 그래프 설정.
    
    Attributes:
        layout_algorithm: 레이아웃 알고리즘 ('spring', 'kamada_kawai', 'circular')
        node_size_metric: 노드 크기 결정 지표 ('degree', 'centrality')
        show_labels: 노드 레이블 표시 여부
        max_nodes: 표시할 최대 노드 수 (None이면 제한 없음)
        edge_opacity: Edge 투명도 (0.0 ~ 1.0)
        community_colors: 커뮤니티별 색상 목록
    """
    layout_algorithm: str = 'spring'
    node_size_metric: str = 'degree'
    show_labels: bool = False
    max_nodes: Optional[int] = None
    edge_opacity: float = 0.3
    community_colors: List[str] = field(default_factory=lambda: DEFAULT_COMMUNITY_COLORS.copy())


def build_network_graph(edge_data: EdgeListData) -> nx.Graph:
    """Edge list 데이터로부터 NetworkX 그래프 생성.
    
    Args:
        edge_data: Edge list 데이터
        
    Returns:
        NetworkX 그래프
    """
    G = nx.Graph()
    
    for _, row in edge_data.df.iterrows():
        source = row['Source']
        target = row['Target']
        weight = row.get('Weight', 1)
        
        G.add_edge(source, target, weight=weight)
    
    return G


def compute_layout(
    G: nx.Graph,
    algorithm: str = 'spring',
    seed: int = 42,
) -> Dict[Any, Tuple[float, float]]:
    """네트워크 레이아웃 계산.
    
    Args:
        G: NetworkX 그래프
        algorithm: 레이아웃 알고리즘 ('spring', 'kamada_kawai', 'circular')
        seed: 랜덤 시드 (재현성 보장)
        
    Returns:
        노드 위치 딕셔너리 {node: (x, y)}
    """
    if len(G.nodes()) == 0:
        return {}
    
    # 알고리즘별 레이아웃 계산
    if algorithm == 'spring':
        # Fruchterman-Reingold force-directed layout
        pos = nx.spring_layout(
            G,
            seed=seed,
            k=None,  # 자동 최적 거리
            iterations=50,
        )
    elif algorithm == 'kamada_kawai':
        try:
            pos = nx.kamada_kawai_layout(G)
        except Exception:
            # 그래프가 연결되지 않은 경우 spring layout fallback
            pos = nx.spring_layout(G, seed=seed)
    elif algorithm == 'circular':
        pos = nx.circular_layout(G)
    else:
        # 기본: spring layout
        pos = nx.spring_layout(G, seed=seed)
    
    return pos


def normalize_values(
    values: List[float],
    min_output: float,
    max_output: float,
) -> List[float]:
    """값 목록을 특정 범위로 정규화.
    
    Args:
        values: 원본 값 목록
        min_output: 출력 최소값
        max_output: 출력 최대값
        
    Returns:
        정규화된 값 목록
    """
    if not values:
        return []
    
    min_val = min(values)
    max_val = max(values)
    
    if max_val == min_val:
        # 모든 값이 동일한 경우 중간값 반환
        return [(min_output + max_output) / 2] * len(values)
    
    return [
        min_output + (v - min_val) / (max_val - min_val) * (max_output - min_output)
        for v in values
    ]


def get_node_sizes(
    G: nx.Graph,
    centrality_data: Optional[CentralityData] = None,
    metric: str = 'degree',
) -> Dict[Any, float]:
    """노드 크기 계산 (Degree 기반).
    
    Args:
        G: NetworkX 그래프
        centrality_data: 중심성 데이터 (선택적)
        metric: 크기 결정 지표 ('degree', 'betweenness', 'closeness')
        
    Returns:
        노드별 크기 딕셔너리
    """
    nodes = list(G.nodes())
    
    if not nodes:
        return {}
    
    # Degree 기반 크기 계산 (기본)
    degrees = [G.degree(n) for n in nodes]
    normalized_sizes = normalize_values(degrees, NODE_SIZE_MIN, NODE_SIZE_MAX)
    
    return dict(zip(nodes, normalized_sizes))


def get_node_colors(
    G: nx.Graph,
    community_data: Optional[CommunityData] = None,
    colors: Optional[List[str]] = None,
) -> Dict[Any, str]:
    """노드 색상 계산 (커뮤니티 기반).
    
    Args:
        G: NetworkX 그래프
        community_data: 커뮤니티 데이터
        colors: 사용할 색상 목록
        
    Returns:
        노드별 색상 딕셔너리
    """
    if colors is None:
        colors = DEFAULT_COMMUNITY_COLORS
    
    nodes = list(G.nodes())
    
    if not nodes:
        return {}
    
    # 커뮤니티 데이터가 있으면 커뮤니티별 색상 할당
    if community_data is not None and not community_data.df.empty:
        node_to_community = {}
        
        if 'node' in community_data.df.columns and 'community_id' in community_data.df.columns:
            node_to_community = dict(zip(
                community_data.df['node'],
                community_data.df['community_id']
            ))
        
        node_colors = {}
        for node in nodes:
            community_id = node_to_community.get(node, 0)
            color_idx = int(community_id) % len(colors)
            node_colors[node] = colors[color_idx]
        
        return node_colors
    
    # 커뮤니티 데이터가 없으면 기본 색상 사용
    return {node: colors[0] for node in nodes}


def get_edge_widths(
    G: nx.Graph,
    edge_data: EdgeListData,
) -> Dict[Tuple[Any, Any], float]:
    """Edge 굵기 계산 (Weight 기반).
    
    Args:
        G: NetworkX 그래프
        edge_data: Edge list 데이터
        
    Returns:
        Edge별 굵기 딕셔너리
    """
    edges = list(G.edges())
    
    if not edges:
        return {}
    
    weights = []
    for u, v in edges:
        weight = G.edges[u, v].get('weight', 1)
        weights.append(weight)
    
    normalized_widths = normalize_values(weights, EDGE_WIDTH_MIN, EDGE_WIDTH_MAX)
    
    return dict(zip(edges, normalized_widths))


def create_edge_traces(
    G: nx.Graph,
    pos: Dict[Any, Tuple[float, float]],
    edge_widths: Dict[Tuple[Any, Any], float],
    edge_opacity: float = 0.3,
) -> List[go.Scatter]:
    """Edge를 그리는 Plotly trace 생성.
    
    Args:
        G: NetworkX 그래프
        pos: 노드 위치
        edge_widths: Edge별 굵기
        edge_opacity: Edge 투명도
        
    Returns:
        Plotly Scatter trace 목록
    """
    edge_traces = []
    
    for edge in G.edges():
        u, v = edge
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        
        width = edge_widths.get(edge, EDGE_WIDTH_MIN)
        weight = G.edges[u, v].get('weight', 1)
        
        edge_trace = go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode='lines',
            line=dict(
                width=width,
                color='#888888',
            ),
            opacity=edge_opacity,
            hoverinfo='text',
            hovertext=f"{u} — {v}<br>Weight: {weight}",
            showlegend=False,
        )
        edge_traces.append(edge_trace)
    
    return edge_traces


def create_node_trace(
    G: nx.Graph,
    pos: Dict[Any, Tuple[float, float]],
    node_sizes: Dict[Any, float],
    node_colors: Dict[Any, str],
    centrality_data: Optional[CentralityData] = None,
    community_data: Optional[CommunityData] = None,
) -> go.Scatter:
    """노드를 그리는 Plotly trace 생성.
    
    Args:
        G: NetworkX 그래프
        pos: 노드 위치
        node_sizes: 노드별 크기
        node_colors: 노드별 색상
        centrality_data: 중심성 데이터 (hover 정보용)
        community_data: 커뮤니티 데이터 (hover 정보용)
        
    Returns:
        Plotly Scatter trace
    """
    nodes = list(G.nodes())
    
    x_coords = [pos[node][0] for node in nodes]
    y_coords = [pos[node][1] for node in nodes]
    sizes = [node_sizes.get(node, NODE_SIZE_MIN) for node in nodes]
    colors = [node_colors.get(node, DEFAULT_COMMUNITY_COLORS[0]) for node in nodes]
    
    # Hover 텍스트 생성
    hover_texts = []
    
    # 중심성 데이터를 딕셔너리로 변환
    centrality_dict = {}
    if centrality_data is not None and not centrality_data.df.empty:
        if 'node' in centrality_data.df.columns:
            for _, row in centrality_data.df.iterrows():
                node = row['node']
                centrality_dict[node] = {
                    'degree': row.get('degree_centrality', 0),
                    'betweenness': row.get('betweenness_centrality', 0),
                    'closeness': row.get('closeness_centrality', 0),
                    'eigenvector': row.get('eigenvector_centrality', None),
                }
    
    # 커뮤니티 데이터를 딕셔너리로 변환
    community_dict = {}
    if community_data is not None and not community_data.df.empty:
        if 'node' in community_data.df.columns and 'community_id' in community_data.df.columns:
            community_dict = dict(zip(
                community_data.df['node'],
                community_data.df['community_id']
            ))
    
    for node in nodes:
        degree = G.degree(node)
        hover_text = f"<b>{node}</b><br>Degree: {degree}"
        
        if node in community_dict:
            hover_text += f"<br>Community: {community_dict[node]}"
        
        if node in centrality_dict:
            c = centrality_dict[node]
            hover_text += f"<br>Degree Centrality: {c['degree']:.4f}"
            hover_text += f"<br>Betweenness: {c['betweenness']:.4f}"
            hover_text += f"<br>Closeness: {c['closeness']:.4f}"
            if c['eigenvector'] is not None:
                hover_text += f"<br>Eigenvector: {c['eigenvector']:.4f}"
        
        hover_texts.append(hover_text)
    
    node_trace = go.Scatter(
        x=x_coords,
        y=y_coords,
        mode='markers',
        marker=dict(
            size=sizes,
            color=colors,
            line=dict(width=1, color='white'),
        ),
        hoverinfo='text',
        hovertext=hover_texts,
        showlegend=False,
    )
    
    return node_trace


def create_network_figure(
    G: nx.Graph,
    pos: Dict[Any, Tuple[float, float]],
    node_sizes: Dict[Any, float],
    node_colors: Dict[Any, str],
    edge_widths: Dict[Tuple[Any, Any], float],
    title: str = "Network Graph",
    centrality_data: Optional[CentralityData] = None,
    community_data: Optional[CommunityData] = None,
    edge_opacity: float = 0.3,
    height: int = 700,
) -> go.Figure:
    """완성된 네트워크 그래프 Figure 생성.
    
    Args:
        G: NetworkX 그래프
        pos: 노드 위치
        node_sizes: 노드별 크기
        node_colors: 노드별 색상
        edge_widths: Edge별 굵기
        title: 그래프 제목
        centrality_data: 중심성 데이터
        community_data: 커뮤니티 데이터
        edge_opacity: Edge 투명도
        height: 그래프 높이 (픽셀)
        
    Returns:
        Plotly Figure 객체
    """
    # Edge traces 생성
    edge_traces = create_edge_traces(G, pos, edge_widths, edge_opacity)
    
    # Node trace 생성
    node_trace = create_node_trace(
        G, pos, node_sizes, node_colors,
        centrality_data, community_data
    )
    
    # Figure 생성
    fig = go.Figure(
        data=edge_traces + [node_trace],
        layout=go.Layout(
            title=dict(
                text=title,
                x=0.5,
                y=0.95,
            ),
            showlegend=False,
            hovermode='closest',
            xaxis=dict(
                showgrid=False,
                zeroline=False,
                showticklabels=False,
                showline=False,
            ),
            yaxis=dict(
                showgrid=False,
                zeroline=False,
                showticklabels=False,
                showline=False,
            ),
            margin=dict(l=10, r=10, t=50, b=10),
            height=height,
            paper_bgcolor='white',
            plot_bgcolor='white',
        )
    )
    
    return fig


def sample_large_network(
    edge_data: EdgeListData,
    max_nodes: int = 200,
) -> EdgeListData:
    """큰 네트워크를 샘플링하여 축소.
    
    Degree 기반으로 상위 노드들만 유지합니다.
    
    Args:
        edge_data: 원본 Edge list 데이터
        max_nodes: 최대 노드 수
        
    Returns:
        샘플링된 EdgeListData
    """
    # 노드별 Degree 계산
    G = build_network_graph(edge_data)
    degrees = dict(G.degree())
    
    # 상위 N개 노드 선택
    top_nodes = sorted(degrees, key=degrees.get, reverse=True)[:max_nodes]
    top_nodes_set = set(top_nodes)
    
    # 선택된 노드들 간의 Edge만 유지
    filtered_df = edge_data.df[
        (edge_data.df['Source'].isin(top_nodes_set)) &
        (edge_data.df['Target'].isin(top_nodes_set))
    ].copy()
    
    return EdgeListData(
        df=filtered_df,
        tsg_group=edge_data.tsg_group,
        time_unit=edge_data.time_unit,
        time_value=edge_data.time_value,
        threshold=edge_data.threshold,
        network_type=edge_data.network_type,
    )


class NetworkGraphComponent:
    """네트워크 그래프 시각화 컴포넌트.
    
    Plotly를 사용하여 인터랙티브 네트워크 그래프를 렌더링합니다.
    
    Attributes:
        config: 그래프 설정
    
    Example:
        >>> component = NetworkGraphComponent()
        >>> component.render(edge_data, community_data, centrality_data)
    """
    
    def __init__(self, config: Optional[NetworkGraphConfig] = None):
        """NetworkGraphComponent 초기화.
        
        Args:
            config: 그래프 설정. None이면 기본 설정 사용.
        """
        self.config = config or NetworkGraphConfig()
    
    def render(
        self,
        edge_data: EdgeListData,
        community_data: Optional[CommunityData] = None,
        centrality_data: Optional[CentralityData] = None,
        title: Optional[str] = None,
        height: int = 700,
        show_controls: bool = True,
    ) -> None:
        """네트워크 그래프를 Streamlit에 렌더링.
        
        Args:
            edge_data: Edge list 데이터
            community_data: 커뮤니티 데이터 (노드 색상용)
            centrality_data: 중심성 데이터 (hover 정보용)
            title: 그래프 제목
            height: 그래프 높이 (픽셀)
            show_controls: 컨트롤 패널 표시 여부
        """
        if edge_data is None or edge_data.df.empty:
            st.warning("표시할 네트워크 데이터가 없습니다.")
            return
        
        # 컨트롤 패널
        if show_controls:
            with st.expander("⚙️ 그래프 설정", expanded=False):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    layout_algorithm = st.selectbox(
                        "레이아웃 알고리즘",
                        options=['spring', 'kamada_kawai', 'circular'],
                        index=0,
                        format_func=lambda x: {
                            'spring': 'Spring (Force-directed)',
                            'kamada_kawai': 'Kamada-Kawai',
                            'circular': 'Circular',
                        }.get(x, x),
                        key="network_layout_algorithm",
                    )
                
                with col2:
                    edge_opacity = st.slider(
                        "Edge 투명도",
                        min_value=0.1,
                        max_value=1.0,
                        value=0.3,
                        step=0.1,
                        key="network_edge_opacity",
                    )
                
                with col3:
                    max_nodes = st.number_input(
                        "최대 노드 수",
                        min_value=10,
                        max_value=1000,
                        value=200,
                        step=50,
                        key="network_max_nodes",
                        help="노드가 많은 경우 Degree 상위 노드만 표시",
                    )
        else:
            layout_algorithm = self.config.layout_algorithm
            edge_opacity = self.config.edge_opacity
            max_nodes = self.config.max_nodes or 200
        
        # 큰 네트워크 샘플링
        current_node_count = edge_data.node_count
        working_edge_data = edge_data
        
        if current_node_count > max_nodes:
            st.info(
                f"네트워크가 크므로 상위 {max_nodes}개 노드만 표시합니다. "
                f"(전체: {current_node_count}개 노드)"
            )
            working_edge_data = sample_large_network(edge_data, max_nodes)
        
        # 네트워크 그래프 생성
        with st.spinner("네트워크 그래프 생성 중..."):
            G = build_network_graph(working_edge_data)
            
            if len(G.nodes()) == 0:
                st.warning("표시할 노드가 없습니다.")
                return
            
            # 레이아웃 계산
            pos = compute_layout(G, algorithm=layout_algorithm, seed=42)
            
            # 노드 속성 계산
            node_sizes = get_node_sizes(G, centrality_data)
            node_colors = get_node_colors(G, community_data, self.config.community_colors)
            edge_widths = get_edge_widths(G, working_edge_data)
            
            # 제목 생성
            if title is None:
                network_type_label = "기업" if working_edge_data.network_type == "company" else "WI"
                title = f"{network_type_label} 협력 네트워크 ({working_edge_data.tsg_group}, {working_edge_data.time_value})"
            
            # Figure 생성
            fig = create_network_figure(
                G=G,
                pos=pos,
                node_sizes=node_sizes,
                node_colors=node_colors,
                edge_widths=edge_widths,
                title=title,
                centrality_data=centrality_data,
                community_data=community_data,
                edge_opacity=edge_opacity,
                height=height,
            )
            
            # 그래프 표시
            st.plotly_chart(fig, use_container_width=True)
        
        # 그래프 정보 표시
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("노드 수", f"{len(G.nodes()):,}")
        col2.metric("Edge 수", f"{len(G.edges()):,}")
        col3.metric("밀도", f"{nx.density(G):.4f}")
        
        if community_data is not None:
            col4.metric("커뮤니티 수", f"{community_data.community_count:,}")


def render_network_graph(
    edge_data: EdgeListData,
    community_data: Optional[CommunityData] = None,
    centrality_data: Optional[CentralityData] = None,
    title: Optional[str] = None,
    height: int = 700,
    show_controls: bool = True,
) -> None:
    """네트워크 그래프 렌더링 헬퍼 함수.
    
    Args:
        edge_data: Edge list 데이터
        community_data: 커뮤니티 데이터
        centrality_data: 중심성 데이터
        title: 그래프 제목
        height: 그래프 높이
        show_controls: 컨트롤 패널 표시 여부
    """
    component = NetworkGraphComponent()
    component.render(
        edge_data=edge_data,
        community_data=community_data,
        centrality_data=centrality_data,
        title=title,
        height=height,
        show_controls=show_controls,
    )


__all__ = [
    # 설정 클래스
    "NetworkGraphConfig",
    # 컴포넌트 클래스
    "NetworkGraphComponent",
    # 헬퍼 함수
    "render_network_graph",
    # 유틸리티 함수
    "build_network_graph",
    "compute_layout",
    "get_node_sizes",
    "get_node_colors",
    "get_edge_widths",
    "create_network_figure",
    "sample_large_network",
    # 상수
    "DEFAULT_COMMUNITY_COLORS",
    "NODE_SIZE_MIN",
    "NODE_SIZE_MAX",
    "EDGE_WIDTH_MIN",
    "EDGE_WIDTH_MAX",
]
