"""
Community View Component

커뮤니티 목록 및 상세 정보를 제공하는 컴포넌트.
커뮤니티 크기, 주요 노드, 구성원 목록 등을 표시.

Requirements: 13.5
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.data_loader import (
    CentralityData,
    CommunityData,
    DashboardDataLoader,
    get_data_loader,
)
from src.dashboard.components.filter_panel import FilterSelection


class CommunityView:
    """커뮤니티 목록 뷰 컴포넌트.
    
    탐지된 커뮤니티 정보를 표시하고 각 커뮤니티의 상세 정보를 제공합니다.
    
    Attributes:
        data_loader: DashboardDataLoader 인스턴스
    """
    
    def __init__(self, data_loader: Optional[DashboardDataLoader] = None):
        """CommunityView 초기화.
        
        Args:
            data_loader: 데이터 로더 인스턴스. None이면 기본 로더 사용.
        """
        self.data_loader = data_loader or get_data_loader()
    
    def _get_community_summary(
        self,
        community_data: CommunityData,
    ) -> pd.DataFrame:
        """커뮤니티 요약 정보 DataFrame 생성.
        
        Args:
            community_data: 커뮤니티 데이터
            
        Returns:
            커뮤니티별 요약 정보 DataFrame
        """
        if community_data.df.empty or "community_id" not in community_data.df.columns:
            return pd.DataFrame()
        
        # 커뮤니티별 집계
        summary = community_data.df.groupby("community_id").agg(
            노드_수=("node", "count"),
            노드_목록=("node", lambda x: list(x)[:5]),  # 상위 5개만
        ).reset_index()
        
        summary.columns = ["커뮤니티 ID", "노드 수", "대표 노드 (상위 5개)"]
        summary["대표 노드 (상위 5개)"] = summary["대표 노드 (상위 5개)"].apply(
            lambda x: ", ".join(str(n) for n in x)
        )
        
        # 크기 순으로 정렬
        summary = summary.sort_values("노드 수", ascending=False).reset_index(drop=True)
        summary.index = summary.index + 1  # 순위로 사용
        
        return summary
    
    def _get_community_members_with_centrality(
        self,
        community_data: CommunityData,
        centrality_data: Optional[CentralityData],
        community_id: int,
    ) -> pd.DataFrame:
        """특정 커뮤니티의 멤버와 중심성 정보 반환.
        
        Args:
            community_data: 커뮤니티 데이터
            centrality_data: 중심성 데이터 (선택적)
            community_id: 커뮤니티 ID
            
        Returns:
            멤버 정보 DataFrame
        """
        members = community_data.get_community_members(community_id)
        
        if not members:
            return pd.DataFrame()
        
        result_df = pd.DataFrame({"node": members})
        
        # 중심성 데이터가 있으면 병합
        if centrality_data is not None and not centrality_data.df.empty:
            centrality_cols = [
                col for col in centrality_data.df.columns
                if "centrality" in col or col == "node"
            ]
            result_df = result_df.merge(
                centrality_data.df[centrality_cols],
                on="node",
                how="left",
            )
            
            # Degree Centrality 기준 정렬
            if "degree_centrality" in result_df.columns:
                result_df = result_df.sort_values(
                    "degree_centrality", ascending=False
                )
        
        return result_df.reset_index(drop=True)
    
    def render_community_overview(
        self,
        community_data: CommunityData,
    ) -> None:
        """커뮤니티 개요 정보 렌더링.
        
        Args:
            community_data: 커뮤니티 데이터
        """
        # 주요 통계 표시
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("탐지된 커뮤니티 수", community_data.community_count)
        
        with col2:
            if community_data.modularity is not None:
                st.metric("모듈성 (Modularity)", f"{community_data.modularity:.4f}")
            else:
                st.metric("모듈성 (Modularity)", "N/A")
        
        with col3:
            sizes = community_data.get_community_sizes()
            if sizes:
                avg_size = sum(sizes.values()) / len(sizes)
                st.metric("평균 커뮤니티 크기", f"{avg_size:.1f}")
            else:
                st.metric("평균 커뮤니티 크기", "N/A")
    
    def render_community_size_chart(
        self,
        community_data: CommunityData,
        top_n: int = 10,
    ) -> None:
        """커뮤니티 크기 막대 차트 렌더링.
        
        Args:
            community_data: 커뮤니티 데이터
            top_n: 표시할 상위 커뮤니티 수
        """
        sizes = community_data.get_community_sizes()
        
        if not sizes:
            st.warning("커뮤니티 크기 데이터가 없습니다.")
            return
        
        # 크기 순 정렬
        sorted_sizes = sorted(sizes.items(), key=lambda x: x[1], reverse=True)[:top_n]
        
        df = pd.DataFrame(sorted_sizes, columns=["커뮤니티 ID", "노드 수"])
        df["커뮤니티"] = df["커뮤니티 ID"].apply(lambda x: f"Community {x}")
        
        fig = px.bar(
            df,
            x="커뮤니티",
            y="노드 수",
            title=f"상위 {top_n}개 커뮤니티 크기",
            color="노드 수",
            color_continuous_scale="Blues",
        )
        
        fig.update_layout(
            height=400,
            xaxis_title="커뮤니티",
            yaxis_title="노드 수",
            showlegend=False,
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def render_community_size_pie(
        self,
        community_data: CommunityData,
        top_n: int = 8,
    ) -> None:
        """커뮤니티 크기 파이 차트 렌더링.
        
        Args:
            community_data: 커뮤니티 데이터
            top_n: 개별 표시할 상위 커뮤니티 수 (나머지는 "기타"로 통합)
        """
        sizes = community_data.get_community_sizes()
        
        if not sizes:
            st.warning("커뮤니티 크기 데이터가 없습니다.")
            return
        
        sorted_sizes = sorted(sizes.items(), key=lambda x: x[1], reverse=True)
        
        # 상위 N개와 기타로 분리
        top_communities = sorted_sizes[:top_n]
        others = sorted_sizes[top_n:]
        
        labels = [f"Community {cid}" for cid, _ in top_communities]
        values = [size for _, size in top_communities]
        
        if others:
            labels.append("기타")
            values.append(sum(size for _, size in others))
        
        fig = go.Figure(data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.4,
                textinfo="label+percent",
                textposition="outside",
            )
        ])
        
        fig.update_layout(
            title="커뮤니티 크기 분포",
            height=450,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.2,
                xanchor="center",
                x=0.5,
            ),
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def render_community_summary_table(
        self,
        community_data: CommunityData,
    ) -> None:
        """커뮤니티 요약 테이블 렌더링.
        
        Args:
            community_data: 커뮤니티 데이터
        """
        summary_df = self._get_community_summary(community_data)
        
        if summary_df.empty:
            st.warning("커뮤니티 요약 데이터가 없습니다.")
            return
        
        st.dataframe(
            summary_df,
            use_container_width=True,
            height=min(400, (len(summary_df) + 1) * 35 + 40),
        )
    
    def render_community_detail(
        self,
        community_data: CommunityData,
        centrality_data: Optional[CentralityData],
        community_id: int,
    ) -> None:
        """특정 커뮤니티 상세 정보 렌더링.
        
        Args:
            community_data: 커뮤니티 데이터
            centrality_data: 중심성 데이터
            community_id: 커뮤니티 ID
        """
        members = community_data.get_community_members(community_id)
        
        if not members:
            st.warning(f"커뮤니티 {community_id}의 멤버 정보가 없습니다.")
            return
        
        # 커뮤니티 기본 정보
        st.write(f"**커뮤니티 {community_id} 상세 정보**")
        st.write(f"- 총 멤버 수: {len(members)}개")
        
        # 멤버 목록 (중심성 포함)
        members_df = self._get_community_members_with_centrality(
            community_data, centrality_data, community_id
        )
        
        if not members_df.empty:
            # 컬럼명 한국어로 변환
            column_labels = {
                "node": "노드",
                "degree_centrality": "연결 중심성",
                "betweenness_centrality": "매개 중심성",
                "closeness_centrality": "근접 중심성",
                "eigenvector_centrality": "고유벡터 중심성",
            }
            
            display_df = members_df.rename(columns=column_labels)
            display_df.index = display_df.index + 1
            
            st.dataframe(
                display_df,
                use_container_width=True,
                height=min(400, (len(display_df) + 1) * 35 + 40),
            )
        else:
            # 중심성 없이 멤버 목록만 표시
            st.write("**멤버 목록:**")
            st.write(", ".join(str(m) for m in members))
    
    def render_community_search(
        self,
        community_data: CommunityData,
        search_query: str,
    ) -> Optional[int]:
        """노드 검색을 통한 커뮤니티 찾기.
        
        Args:
            community_data: 커뮤니티 데이터
            search_query: 검색 쿼리
            
        Returns:
            발견된 커뮤니티 ID 또는 None
        """
        if not search_query or community_data.df.empty:
            return None
        
        # 노드 검색
        mask = community_data.df["node"].str.lower().str.contains(
            search_query.lower(), na=False
        )
        matched = community_data.df[mask]
        
        if matched.empty:
            st.info(f"'{search_query}'에 해당하는 노드를 찾을 수 없습니다.")
            return None
        
        st.success(f"🔍 '{search_query}' 검색 결과: {len(matched)}개 노드")
        
        # 검색 결과 표시
        result_df = matched[["node", "community_id"]].copy()
        result_df.columns = ["노드", "커뮤니티 ID"]
        result_df = result_df.reset_index(drop=True)
        result_df.index = result_df.index + 1
        
        st.dataframe(result_df, use_container_width=True, height=200)
        
        # 첫 번째 결과의 커뮤니티 ID 반환
        return int(matched.iloc[0]["community_id"])
    
    def render(
        self,
        selection: FilterSelection,
    ) -> None:
        """커뮤니티 탭 전체 렌더링.
        
        Args:
            selection: 필터 선택 값
        """
        # 커뮤니티 데이터 로드
        community_data = self.data_loader.load_community(
            selection.tsg_group,
            selection.time_unit,
            selection.time_value,
        )
        
        # 중심성 데이터도 로드 (상세 정보에서 사용)
        centrality_data = self.data_loader.load_centrality(
            selection.tsg_group,
            selection.time_unit,
            selection.time_value,
        )
        
        if community_data is None or community_data.df.empty:
            st.warning(
                f"⚠️ 선택한 조건에 해당하는 커뮤니티 데이터가 없습니다.\n\n"
                f"- TSG 그룹: {selection.tsg_group}\n"
                f"- 시간 단위: {selection.time_unit}\n"
                f"- 시간 값: {selection.time_value}\n\n"
                f"파이프라인을 실행하여 분석 결과를 생성하세요."
            )
            return
        
        st.subheader("👥 커뮤니티 분석")
        
        # 개요 정보
        self.render_community_overview(community_data)
        
        st.markdown("---")
        
        # 노드로 커뮤니티 검색
        st.write("**🔍 노드로 커뮤니티 찾기**")
        search_col1, search_col2 = st.columns([3, 1])
        
        with search_col1:
            search_query = st.text_input(
                "노드 이름 입력",
                placeholder="예: Samsung, Huawei, Nokia...",
                key="community_search_input",
                label_visibility="collapsed",
            )
        
        with search_col2:
            st.button("검색", key="community_search_button")
        
        found_community = None
        if search_query:
            found_community = self.render_community_search(community_data, search_query)
        
        st.markdown("---")
        
        # 시각화 탭
        viz_tab1, viz_tab2, viz_tab3 = st.tabs([
            "📊 크기 분포", "📋 커뮤니티 목록", "🔍 커뮤니티 상세"
        ])
        
        with viz_tab1:
            chart_type = st.radio(
                "차트 유형",
                ["막대 차트", "파이 차트"],
                horizontal=True,
                key="community_chart_type",
            )
            
            if chart_type == "막대 차트":
                top_n_bar = st.slider(
                    "표시할 커뮤니티 수",
                    min_value=5,
                    max_value=min(20, community_data.community_count),
                    value=10,
                    key="community_bar_top_n",
                )
                self.render_community_size_chart(community_data, top_n_bar)
            else:
                top_n_pie = st.slider(
                    "개별 표시할 커뮤니티 수 (나머지는 '기타'로 통합)",
                    min_value=3,
                    max_value=min(10, community_data.community_count),
                    value=8,
                    key="community_pie_top_n",
                )
                self.render_community_size_pie(community_data, top_n_pie)
        
        with viz_tab2:
            st.write("**커뮤니티 목록 (크기 순)**")
            self.render_community_summary_table(community_data)
        
        with viz_tab3:
            # 검색 결과가 있으면 해당 커뮤니티를 기본 선택
            largest_communities = community_data.get_largest_communities(
                min(10, community_data.community_count)
            )
            community_options = [cid for cid, _ in largest_communities]
            
            default_index = 0
            if found_community is not None and found_community in community_options:
                default_index = community_options.index(found_community)
            
            selected_community = st.selectbox(
                "커뮤니티 선택",
                community_options,
                index=default_index,
                format_func=lambda x: f"Community {x} (크기: {community_data.get_community_sizes().get(x, 0)})",
                key="community_detail_select",
            )
            
            if selected_community is not None:
                self.render_community_detail(
                    community_data,
                    centrality_data,
                    selected_community,
                )


def render_community_view(
    selection: FilterSelection,
    data_loader: Optional[DashboardDataLoader] = None,
) -> None:
    """커뮤니티 뷰를 렌더링하는 헬퍼 함수.
    
    Args:
        selection: 필터 선택 값
        data_loader: 데이터 로더. None이면 기본 로더 사용.
    """
    view = CommunityView(data_loader)
    view.render(selection)


__all__ = [
    "CommunityView",
    "render_community_view",
]
