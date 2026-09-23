"""
Centrality Table Component

Centrality 순위 테이블을 제공하는 컴포넌트.
Degree, Betweenness, Closeness, Eigenvector Centrality 표시 및 검색 기능 제공.

Requirements: 13.4
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.data_loader import (
    CentralityData,
    DashboardDataLoader,
    get_data_loader,
)
from src.dashboard.components.filter_panel import FilterSelection


# 중심성 지표 라벨 및 설명 매핑 (한국어)
CENTRALITY_LABELS = {
    "node": "노드",
    "degree_centrality": "연결 중심성 (Degree)",
    "betweenness_centrality": "매개 중심성 (Betweenness)",
    "closeness_centrality": "근접 중심성 (Closeness)",
    "eigenvector_centrality": "고유벡터 중심성 (Eigenvector)",
}

CENTRALITY_DESCRIPTIONS = {
    "degree_centrality": "직접 연결된 이웃 노드 수 기반. 값이 클수록 많은 노드와 직접 연결됨.",
    "betweenness_centrality": "다른 노드 쌍 간 최단 경로에 위치하는 빈도 기반. 값이 클수록 정보 흐름의 중개자 역할.",
    "closeness_centrality": "모든 다른 노드까지의 평균 최단 거리의 역수. 값이 클수록 네트워크 중심에 위치.",
    "eigenvector_centrality": "연결된 노드의 중요도를 반영. 값이 클수록 중요한 노드들과 연결됨.",
}

CENTRALITY_METRICS = [
    "degree_centrality",
    "betweenness_centrality",
    "closeness_centrality",
    "eigenvector_centrality",
]


class CentralityTable:
    """Centrality 순위 테이블 컴포넌트.
    
    중심성 지표별 상위 노드를 테이블로 표시하고 검색 기능을 제공합니다.
    
    Attributes:
        data_loader: DashboardDataLoader 인스턴스
    """
    
    def __init__(self, data_loader: Optional[DashboardDataLoader] = None):
        """CentralityTable 초기화.
        
        Args:
            data_loader: 데이터 로더 인스턴스. None이면 기본 로더 사용.
        """
        self.data_loader = data_loader or get_data_loader()
    
    def _format_centrality_value(self, value: float) -> str:
        """중심성 값을 포맷팅."""
        if pd.isna(value):
            return "N/A"
        return f"{value:.4f}"
    
    def _add_rank_column(
        self,
        df: pd.DataFrame,
        metric: str,
    ) -> pd.DataFrame:
        """지정된 중심성 지표 기준 순위 컬럼 추가."""
        result_df = df.copy()
        result_df[f"{metric}_rank"] = result_df[metric].rank(
            ascending=False, method="min"
        ).astype(int)
        return result_df
    
    def render_top_n_table(
        self,
        centrality_data: CentralityData,
        metric: str = "degree_centrality",
        top_n: int = 20,
    ) -> None:
        """상위 N개 노드의 중심성 테이블 렌더링.
        
        Args:
            centrality_data: 중심성 데이터
            metric: 정렬 기준 중심성 지표
            top_n: 표시할 상위 노드 수
        """
        if centrality_data.df.empty or metric not in centrality_data.df.columns:
            st.warning(f"'{CENTRALITY_LABELS.get(metric, metric)}' 데이터가 없습니다.")
            return
        
        # 상위 N개 선택
        df = centrality_data.get_top_n(metric, top_n)
        
        if df.empty:
            st.warning("표시할 데이터가 없습니다.")
            return
        
        # 순위 추가
        df = self._add_rank_column(df, metric)
        
        # 표시할 컬럼 선택 및 순서 정렬
        display_columns = ["node", f"{metric}_rank"] + [
            col for col in CENTRALITY_METRICS if col in df.columns
        ]
        display_df = df[display_columns].copy()
        
        # 컬럼명 한국어로 변환
        display_df.columns = [
            "순위" if col.endswith("_rank")
            else CENTRALITY_LABELS.get(col, col)
            for col in display_df.columns
        ]
        
        # 인덱스 리셋
        display_df = display_df.reset_index(drop=True)
        display_df.index = display_df.index + 1  # 1부터 시작
        
        st.dataframe(
            display_df,
            use_container_width=True,
            height=min(400, (top_n + 1) * 35 + 40),
        )
    
    def render_full_ranking_table(
        self,
        centrality_data: CentralityData,
        metric: str = "degree_centrality",
    ) -> None:
        """전체 노드의 중심성 순위 테이블 렌더링.
        
        Args:
            centrality_data: 중심성 데이터
            metric: 정렬 기준 중심성 지표
        """
        if centrality_data.df.empty:
            st.warning("표시할 데이터가 없습니다.")
            return
        
        # 정렬 및 순위 추가
        df = centrality_data.df.sort_values(metric, ascending=False).copy()
        df = self._add_rank_column(df, metric)
        
        # 표시할 컬럼 선택
        display_columns = ["node", f"{metric}_rank"] + [
            col for col in CENTRALITY_METRICS if col in df.columns
        ]
        display_df = df[display_columns].copy()
        
        # 컬럼명 한국어로 변환
        display_df.columns = [
            "순위" if col.endswith("_rank")
            else CENTRALITY_LABELS.get(col, col)
            for col in display_df.columns
        ]
        
        display_df = display_df.reset_index(drop=True)
        display_df.index = display_df.index + 1
        
        st.dataframe(
            display_df,
            use_container_width=True,
            height=600,
        )
    
    def render_search_result(
        self,
        centrality_data: CentralityData,
        search_query: str,
    ) -> None:
        """검색 결과 테이블 렌더링.
        
        Args:
            centrality_data: 중심성 데이터
            search_query: 검색 쿼리 문자열
        """
        if not search_query:
            return
        
        # 검색 실행
        result_df = centrality_data.search_node(search_query)
        
        if result_df.empty:
            st.info(f"'{search_query}'에 해당하는 노드를 찾을 수 없습니다.")
            return
        
        st.success(f"🔍 '{search_query}' 검색 결과: {len(result_df)}개 노드")
        
        # 각 중심성 지표별 순위 계산
        full_df = centrality_data.df.copy()
        for metric in CENTRALITY_METRICS:
            if metric in full_df.columns:
                full_df[f"{metric}_rank"] = full_df[metric].rank(
                    ascending=False, method="min"
                ).astype(int)
        
        # 검색 결과와 순위 병합
        display_df = result_df.merge(
            full_df[["node"] + [f"{m}_rank" for m in CENTRALITY_METRICS if f"{m}_rank" in full_df.columns]],
            on="node",
            how="left",
        )
        
        # 표시 컬럼 구성
        display_columns = ["node"]
        for metric in CENTRALITY_METRICS:
            if metric in display_df.columns:
                display_columns.append(metric)
                rank_col = f"{metric}_rank"
                if rank_col in display_df.columns:
                    display_columns.append(rank_col)
        
        display_df = display_df[display_columns].copy()
        
        # 컬럼명 한국어로 변환 (순위 컬럼 포함)
        new_columns = []
        for col in display_df.columns:
            if col.endswith("_rank"):
                metric_name = col.replace("_rank", "")
                short_label = {
                    "degree_centrality": "연결",
                    "betweenness_centrality": "매개",
                    "closeness_centrality": "근접",
                    "eigenvector_centrality": "고유벡터",
                }.get(metric_name, metric_name)
                new_columns.append(f"{short_label} 순위")
            else:
                new_columns.append(CENTRALITY_LABELS.get(col, col))
        
        display_df.columns = new_columns
        
        st.dataframe(
            display_df,
            use_container_width=True,
            height=min(400, (len(display_df) + 1) * 35 + 40),
        )
    
    def render_centrality_comparison_chart(
        self,
        centrality_data: CentralityData,
        nodes: List[str],
    ) -> None:
        """선택된 노드들의 중심성 비교 레이더 차트 렌더링.
        
        Args:
            centrality_data: 중심성 데이터
            nodes: 비교할 노드 목록
        """
        if not nodes or centrality_data.df.empty:
            return
        
        # 선택된 노드 데이터 필터링
        df = centrality_data.df[centrality_data.df["node"].isin(nodes)].copy()
        
        if df.empty:
            st.warning("선택한 노드의 데이터가 없습니다.")
            return
        
        # 사용 가능한 중심성 지표
        available_metrics = [m for m in CENTRALITY_METRICS if m in df.columns]
        
        if not available_metrics:
            st.warning("비교할 중심성 지표가 없습니다.")
            return
        
        # 레이더 차트용 데이터 준비
        metric_labels = [CENTRALITY_LABELS.get(m, m).split("(")[0].strip() for m in available_metrics]
        
        fig = go.Figure()
        
        colors = px.colors.qualitative.Set2
        
        for idx, (_, row) in enumerate(df.iterrows()):
            values = [row[m] for m in available_metrics]
            # 닫힌 형태로 만들기
            values_closed = values + [values[0]]
            labels_closed = metric_labels + [metric_labels[0]]
            
            fig.add_trace(
                go.Scatterpolar(
                    r=values_closed,
                    theta=labels_closed,
                    fill="toself",
                    name=row["node"],
                    line=dict(color=colors[idx % len(colors)]),
                    opacity=0.7,
                )
            )
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 1]),
            ),
            showlegend=True,
            title="중심성 비교 레이더 차트",
            height=500,
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def render_centrality_distribution(
        self,
        centrality_data: CentralityData,
        metric: str = "degree_centrality",
    ) -> None:
        """중심성 분포 히스토그램 렌더링.
        
        Args:
            centrality_data: 중심성 데이터
            metric: 중심성 지표
        """
        if centrality_data.df.empty or metric not in centrality_data.df.columns:
            st.warning("분포를 표시할 데이터가 없습니다.")
            return
        
        metric_label = CENTRALITY_LABELS.get(metric, metric)
        
        fig = px.histogram(
            centrality_data.df,
            x=metric,
            nbins=30,
            title=f"{metric_label} 분포",
            labels={metric: metric_label},
        )
        
        fig.update_layout(
            height=350,
            xaxis_title=metric_label,
            yaxis_title="빈도",
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def render(
        self,
        selection: FilterSelection,
    ) -> None:
        """중심성 탭 전체 렌더링.
        
        Args:
            selection: 필터 선택 값
        """
        # 중심성 데이터 로드
        centrality_data = self.data_loader.load_centrality(
            selection.tsg_group,
            selection.time_unit,
            selection.time_value,
        )
        
        if centrality_data is None or centrality_data.df.empty:
            st.warning(
                f"⚠️ 선택한 조건에 해당하는 중심성 데이터가 없습니다.\n\n"
                f"- TSG 그룹: {selection.tsg_group}\n"
                f"- 시간 단위: {selection.time_unit}\n"
                f"- 시간 값: {selection.time_value}\n\n"
                f"파이프라인을 실행하여 분석 결과를 생성하세요."
            )
            return
        
        st.subheader("🏆 중심성 순위 분석")
        
        # 노드 검색 영역
        st.write("**🔍 노드 검색**")
        search_col1, search_col2 = st.columns([3, 1])
        
        with search_col1:
            search_query = st.text_input(
                "노드 이름으로 검색",
                placeholder="예: Samsung, Huawei, Nokia...",
                key="centrality_search_input",
                label_visibility="collapsed",
            )
        
        with search_col2:
            search_button = st.button("검색", key="centrality_search_button")
        
        # 검색 결과 표시
        if search_query or search_button:
            self.render_search_result(centrality_data, search_query)
            st.markdown("---")
        
        # 중심성 지표 선택
        st.write("**📊 중심성 순위표**")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            available_metrics = [
                m for m in CENTRALITY_METRICS
                if m in centrality_data.df.columns
            ]
            
            selected_metric = st.selectbox(
                "정렬 기준",
                available_metrics,
                format_func=lambda x: CENTRALITY_LABELS.get(x, x),
                key="centrality_metric_select",
            )
        
        with col2:
            top_n = st.number_input(
                "상위 N개",
                min_value=5,
                max_value=100,
                value=20,
                step=5,
                key="centrality_top_n",
            )
        
        # 지표 설명 표시
        if selected_metric:
            st.caption(f"📌 {CENTRALITY_DESCRIPTIONS.get(selected_metric, '')}")
        
        # 상위 N개 테이블
        self.render_top_n_table(centrality_data, selected_metric, top_n)
        
        st.markdown("---")
        
        # 고급 분석 옵션
        with st.expander("📊 고급 분석 옵션"):
            analysis_tab1, analysis_tab2, analysis_tab3 = st.tabs([
                "분포 시각화", "노드 비교", "전체 데이터"
            ])
            
            with analysis_tab1:
                st.write("**중심성 분포**")
                dist_metric = st.selectbox(
                    "분포를 볼 지표",
                    available_metrics,
                    format_func=lambda x: CENTRALITY_LABELS.get(x, x),
                    key="centrality_dist_metric",
                )
                self.render_centrality_distribution(centrality_data, dist_metric)
            
            with analysis_tab2:
                st.write("**노드 중심성 비교**")
                
                # 노드 선택을 위한 상위 10개 + 직접 입력
                top_10_nodes = centrality_data.get_top_n(selected_metric, 10)["node"].tolist()
                
                compare_nodes = st.multiselect(
                    "비교할 노드 선택 (최대 5개)",
                    options=centrality_data.df["node"].tolist(),
                    default=top_10_nodes[:3] if len(top_10_nodes) >= 3 else top_10_nodes,
                    max_selections=5,
                    key="centrality_compare_nodes",
                )
                
                if compare_nodes:
                    self.render_centrality_comparison_chart(centrality_data, compare_nodes)
            
            with analysis_tab3:
                st.write("**전체 중심성 데이터**")
                self.render_full_ranking_table(centrality_data, selected_metric)


def render_centrality_table(
    selection: FilterSelection,
    data_loader: Optional[DashboardDataLoader] = None,
) -> None:
    """중심성 테이블을 렌더링하는 헬퍼 함수.
    
    Args:
        selection: 필터 선택 값
        data_loader: 데이터 로더. None이면 기본 로더 사용.
    """
    table = CentralityTable(data_loader)
    table.render(selection)


__all__ = [
    "CentralityTable",
    "render_centrality_table",
    "CENTRALITY_LABELS",
    "CENTRALITY_DESCRIPTIONS",
    "CENTRALITY_METRICS",
]
