"""
Statistics Chart Component

시계열 통계 라인 차트를 제공하는 컴포넌트.
노드 수, Edge 수, 밀도 등 네트워크 지표의 시간에 따른 변화를 시각화.

Requirements: 13.3
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.dashboard.data_loader import (
    DashboardDataLoader,
    StatisticsData,
    get_data_loader,
)
from src.dashboard.components.filter_panel import FilterSelection


# 지표 라벨 및 설명 매핑 (한국어)
METRIC_LABELS = {
    "nodes": "노드 수",
    "edges": "Edge 수",
    "weighted_edges": "총 Weight",
    "avg_degree": "평균 연결 수",
    "avg_weighted_degree": "평균 가중 연결 수",
    "density": "밀도",
    "connected_components": "연결 컴포넌트 수",
    "diameter": "직경",
    "avg_path_length": "평균 경로 길이",
    "modularity": "모듈성",
    "avg_clustering_coefficient": "평균 군집 계수",
}

METRIC_DESCRIPTIONS = {
    "nodes": "네트워크에 참여한 노드(기업 또는 WI)의 수",
    "edges": "노드 간 연결선의 수",
    "weighted_edges": "모든 연결선의 가중치 합계",
    "avg_degree": "노드당 평균 연결 수",
    "avg_weighted_degree": "가중치를 고려한 노드당 평균 연결 수",
    "density": "가능한 연결 중 실제 연결의 비율 (0~1)",
    "connected_components": "분리된 네트워크 구성요소의 수",
    "diameter": "가장 긴 최단 경로의 길이",
    "avg_path_length": "노드 간 평균 최단 경로 길이",
    "modularity": "커뮤니티 구조의 품질 지표 (-1~1)",
    "avg_clustering_coefficient": "노드 이웃 간 연결 정도 (0~1)",
}

# 지표 그룹 분류
METRIC_GROUPS = {
    "기본 규모": ["nodes", "edges", "weighted_edges"],
    "연결성": ["avg_degree", "avg_weighted_degree", "density"],
    "구조적 특성": ["connected_components", "diameter", "avg_path_length"],
    "커뮤니티 특성": ["modularity", "avg_clustering_coefficient"],
}


class StatisticsChart:
    """시계열 통계 라인 차트 컴포넌트.
    
    시간에 따른 네트워크 통계 지표 변화를 라인 차트로 시각화합니다.
    TSG 그룹별 비교 뷰도 지원합니다.
    
    Attributes:
        data_loader: DashboardDataLoader 인스턴스
    """
    
    def __init__(self, data_loader: Optional[DashboardDataLoader] = None):
        """StatisticsChart 초기화.
        
        Args:
            data_loader: 데이터 로더 인스턴스. None이면 기본 로더 사용.
        """
        self.data_loader = data_loader or get_data_loader()
    
    def _get_time_column(self, df: pd.DataFrame) -> str:
        """DataFrame에서 시간 컬럼명 반환."""
        for col in ["time_value", "year", "release", "quarter"]:
            if col in df.columns:
                return col
        # 첫 번째 컬럼을 시간 컬럼으로 가정
        return df.columns[0]
    
    def _prepare_chart_data(
        self,
        stats_data: StatisticsData,
        metrics: List[str],
    ) -> pd.DataFrame:
        """차트용 데이터 준비.
        
        Args:
            stats_data: 통계 데이터
            metrics: 표시할 지표 목록
            
        Returns:
            차트용 DataFrame
        """
        df = stats_data.df.copy()
        time_col = self._get_time_column(df)
        
        # 필요한 컬럼만 선택
        available_metrics = [m for m in metrics if m in df.columns]
        columns = [time_col] + available_metrics
        chart_df = df[columns].copy()
        
        # 시간 컬럼으로 정렬
        chart_df = chart_df.sort_values(time_col)
        
        return chart_df
    
    def render_single_metric_chart(
        self,
        stats_data: StatisticsData,
        metric: str,
        title: Optional[str] = None,
        height: int = 400,
    ) -> None:
        """단일 지표의 시계열 차트 렌더링.
        
        Args:
            stats_data: 통계 데이터
            metric: 표시할 지표명
            title: 차트 제목
            height: 차트 높이 (픽셀)
        """
        if metric not in stats_data.df.columns:
            st.warning(f"지표 '{metric}'을(를) 찾을 수 없습니다.")
            return
        
        chart_df = self._prepare_chart_data(stats_data, [metric])
        time_col = self._get_time_column(chart_df)
        
        metric_label = METRIC_LABELS.get(metric, metric)
        chart_title = title or f"{metric_label} 변화 추이"
        
        fig = px.line(
            chart_df,
            x=time_col,
            y=metric,
            title=chart_title,
            labels={
                time_col: "시간",
                metric: metric_label,
            },
            markers=True,
        )
        
        fig.update_layout(
            height=height,
            xaxis_title=f"시간 ({stats_data.time_unit})",
            yaxis_title=metric_label,
            hovermode="x unified",
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def render_multi_metric_chart(
        self,
        stats_data: StatisticsData,
        metrics: List[str],
        title: Optional[str] = None,
        height: int = 500,
        normalize: bool = False,
    ) -> None:
        """다중 지표의 시계열 차트 렌더링.
        
        Args:
            stats_data: 통계 데이터
            metrics: 표시할 지표 목록
            title: 차트 제목
            height: 차트 높이 (픽셀)
            normalize: 0-1 정규화 여부
        """
        available_metrics = [m for m in metrics if m in stats_data.df.columns]
        
        if not available_metrics:
            st.warning("선택한 지표가 데이터에 없습니다.")
            return
        
        chart_df = self._prepare_chart_data(stats_data, available_metrics)
        time_col = self._get_time_column(chart_df)
        
        # 정규화 옵션
        if normalize:
            for metric in available_metrics:
                min_val = chart_df[metric].min()
                max_val = chart_df[metric].max()
                if max_val > min_val:
                    chart_df[metric] = (chart_df[metric] - min_val) / (max_val - min_val)
        
        # Melt하여 long format으로 변환
        melted_df = chart_df.melt(
            id_vars=[time_col],
            value_vars=available_metrics,
            var_name="지표",
            value_name="값",
        )
        
        # 지표명을 한국어로 변환
        melted_df["지표"] = melted_df["지표"].map(
            lambda x: METRIC_LABELS.get(x, x)
        )
        
        chart_title = title or "네트워크 지표 변화 추이"
        
        fig = px.line(
            melted_df,
            x=time_col,
            y="값",
            color="지표",
            title=chart_title,
            labels={time_col: "시간", "값": "정규화된 값" if normalize else "값"},
            markers=True,
        )
        
        fig.update_layout(
            height=height,
            xaxis_title=f"시간 ({stats_data.time_unit})",
            hovermode="x unified",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
            ),
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def render_tsg_comparison_chart(
        self,
        time_unit: str,
        metric: str,
        tsg_groups: Optional[List[str]] = None,
        title: Optional[str] = None,
        height: int = 500,
    ) -> None:
        """TSG 그룹별 비교 차트 렌더링.
        
        Args:
            time_unit: 시간 단위
            metric: 비교할 지표명
            tsg_groups: 비교할 TSG 그룹 목록. None이면 모든 그룹.
            title: 차트 제목
            height: 차트 높이 (픽셀)
        """
        if tsg_groups is None:
            tsg_groups = ["ALL", "RAN", "SA", "CT"]
        
        # 각 TSG 그룹의 통계 데이터 로드
        combined_df = pd.DataFrame()
        
        for tsg in tsg_groups:
            stats_data = self.data_loader.load_statistics(tsg, time_unit)
            if stats_data and metric in stats_data.df.columns:
                df = stats_data.df.copy()
                time_col = self._get_time_column(df)
                df = df[[time_col, metric]].copy()
                df["TSG"] = tsg
                combined_df = pd.concat([combined_df, df], ignore_index=True)
        
        if combined_df.empty:
            st.warning("선택한 조건에 해당하는 데이터가 없습니다.")
            return
        
        time_col = self._get_time_column(combined_df)
        combined_df = combined_df.sort_values(time_col)
        
        metric_label = METRIC_LABELS.get(metric, metric)
        chart_title = title or f"TSG 그룹별 {metric_label} 비교"
        
        fig = px.line(
            combined_df,
            x=time_col,
            y=metric,
            color="TSG",
            title=chart_title,
            labels={time_col: "시간", metric: metric_label},
            markers=True,
        )
        
        fig.update_layout(
            height=height,
            xaxis_title=f"시간 ({time_unit})",
            yaxis_title=metric_label,
            hovermode="x unified",
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def render_dashboard_grid(
        self,
        stats_data: StatisticsData,
        height: int = 800,
    ) -> None:
        """지표 그룹별 그리드 차트 렌더링.
        
        Args:
            stats_data: 통계 데이터
            height: 전체 그리드 높이 (픽셀)
        """
        # 데이터에 있는 지표만 선택
        available_groups = {}
        for group_name, metrics in METRIC_GROUPS.items():
            available_metrics = [m for m in metrics if m in stats_data.df.columns]
            if available_metrics:
                available_groups[group_name] = available_metrics
        
        if not available_groups:
            st.warning("표시할 지표가 없습니다.")
            return
        
        time_col = self._get_time_column(stats_data.df)
        chart_df = stats_data.df.sort_values(time_col)
        
        # 2열 그리드 레이아웃
        num_groups = len(available_groups)
        rows = (num_groups + 1) // 2
        
        fig = make_subplots(
            rows=rows,
            cols=2,
            subplot_titles=list(available_groups.keys()),
            vertical_spacing=0.12,
            horizontal_spacing=0.08,
        )
        
        colors = px.colors.qualitative.Set2
        
        for idx, (group_name, metrics) in enumerate(available_groups.items()):
            row = idx // 2 + 1
            col = idx % 2 + 1
            
            for metric_idx, metric in enumerate(metrics):
                color = colors[metric_idx % len(colors)]
                metric_label = METRIC_LABELS.get(metric, metric)
                
                fig.add_trace(
                    go.Scatter(
                        x=chart_df[time_col],
                        y=chart_df[metric],
                        name=metric_label,
                        mode="lines+markers",
                        marker=dict(size=6),
                        line=dict(color=color),
                        legendgroup=group_name,
                        showlegend=True,
                    ),
                    row=row,
                    col=col,
                )
        
        fig.update_layout(
            height=height,
            title_text=f"네트워크 지표 대시보드 ({stats_data.tsg_group}, {stats_data.time_unit})",
            hovermode="x unified",
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def render(
        self,
        selection: FilterSelection,
        show_comparison: bool = False,
    ) -> None:
        """통계 차트 탭 전체 렌더링.
        
        Args:
            selection: 필터 선택 값
            show_comparison: TSG 그룹 비교 뷰 표시 여부
        """
        # 통계 데이터 로드
        stats_data = self.data_loader.load_statistics(
            selection.tsg_group,
            selection.time_unit,
        )
        
        if stats_data is None or stats_data.df.empty:
            st.warning(
                f"⚠️ 선택한 조건에 해당하는 통계 데이터가 없습니다.\n\n"
                f"- TSG 그룹: {selection.tsg_group}\n"
                f"- 시간 단위: {selection.time_unit}\n\n"
                f"파이프라인을 실행하여 분석 결과를 생성하세요."
            )
            return
        
        # 차트 옵션 선택
        st.subheader("📈 시계열 통계 차트")
        
        chart_mode = st.radio(
            "차트 모드",
            ["단일 지표", "다중 지표 비교", "TSG 그룹 비교", "대시보드"],
            horizontal=True,
            key="stats_chart_mode",
        )
        
        if chart_mode == "단일 지표":
            # 지표 선택
            available_metrics = [
                m for m in METRIC_LABELS.keys()
                if m in stats_data.df.columns
            ]
            
            metric = st.selectbox(
                "지표 선택",
                available_metrics,
                format_func=lambda x: METRIC_LABELS.get(x, x),
                key="single_metric_select",
            )
            
            if metric:
                # 지표 설명 표시
                st.caption(METRIC_DESCRIPTIONS.get(metric, ""))
                self.render_single_metric_chart(stats_data, metric)
        
        elif chart_mode == "다중 지표 비교":
            # 지표 그룹 또는 개별 지표 선택
            st.write("**지표 그룹 선택:**")
            
            selected_groups = []
            cols = st.columns(len(METRIC_GROUPS))
            
            for idx, (group_name, metrics) in enumerate(METRIC_GROUPS.items()):
                with cols[idx]:
                    if st.checkbox(group_name, key=f"group_{group_name}"):
                        selected_groups.extend(metrics)
            
            if not selected_groups:
                # 기본 선택
                selected_groups = ["nodes", "edges", "density"]
            
            normalize = st.checkbox(
                "값 정규화 (0-1 스케일)",
                value=True,
                key="normalize_metrics",
            )
            
            self.render_multi_metric_chart(
                stats_data,
                selected_groups,
                normalize=normalize,
            )
        
        elif chart_mode == "TSG 그룹 비교":
            col1, col2 = st.columns([1, 1])
            
            with col1:
                # 지표 선택
                available_metrics = [
                    m for m in METRIC_LABELS.keys()
                    if m in stats_data.df.columns
                ]
                
                metric = st.selectbox(
                    "비교할 지표",
                    available_metrics,
                    format_func=lambda x: METRIC_LABELS.get(x, x),
                    key="comparison_metric_select",
                )
            
            with col2:
                # TSG 그룹 선택
                tsg_options = ["ALL", "RAN", "SA", "CT"]
                selected_tsg = st.multiselect(
                    "TSG 그룹",
                    tsg_options,
                    default=tsg_options,
                    key="comparison_tsg_select",
                )
            
            if metric and selected_tsg:
                self.render_tsg_comparison_chart(
                    selection.time_unit,
                    metric,
                    selected_tsg,
                )
        
        else:  # 대시보드
            self.render_dashboard_grid(stats_data)
        
        # 원본 데이터 보기 (접기 가능)
        with st.expander("📋 원본 통계 데이터 보기"):
            # 컬럼명을 한국어로 변환
            display_df = stats_data.df.copy()
            display_df.columns = [METRIC_LABELS.get(col, col) for col in display_df.columns]
            st.dataframe(display_df, use_container_width=True, height=300)


def render_statistics_chart(
    selection: FilterSelection,
    data_loader: Optional[DashboardDataLoader] = None,
) -> None:
    """통계 차트를 렌더링하는 헬퍼 함수.
    
    Args:
        selection: 필터 선택 값
        data_loader: 데이터 로더. None이면 기본 로더 사용.
    """
    chart = StatisticsChart(data_loader)
    chart.render(selection)


__all__ = [
    "StatisticsChart",
    "render_statistics_chart",
    "METRIC_LABELS",
    "METRIC_DESCRIPTIONS",
    "METRIC_GROUPS",
]
