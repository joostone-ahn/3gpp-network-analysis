"""
Config Loader 모듈 단위 테스트 및 Property-based 테스트.

Task 1.6: Config Loader 단위 테스트 작성
- YAML 로드 검증
- dataclass 변환 검증
- 각 설정 파일별 로드 테스트
- Property-based testing with Hypothesis

Requirements: 17.1, 17.2
"""

import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml
from hypothesis import assume, given, settings, strategies as st

from src.utils.config_loader import (
    AnalysisConfig,
    CollectorConfig,
    CollectorTarget,
    ConfigLoader,
    DateRange,
    NetworkConfig,
    NormalizationConfig,
    PipelineConfig,
    PreprocessingConfig,
    SourceCleaningConfig,
    load_config,
    load_raw_yaml,
)


class TestConfigLoaderInit:
    """ConfigLoader 초기화 테스트."""

    def test_default_config_dir(self) -> None:
        """기본 config 디렉토리가 올바르게 설정되는지 확인."""
        loader = ConfigLoader()
        assert loader.config_dir.name == "config"
        assert loader.config_dir.exists()

    def test_custom_config_dir(self, tmp_path: Path) -> None:
        """사용자 정의 config 디렉토리가 올바르게 설정되는지 확인."""
        loader = ConfigLoader(config_dir=tmp_path)
        assert loader.config_dir == tmp_path


class TestLoadCollectorConfig:
    """Collector 설정 로드 테스트."""

    def test_load_collector_config(self) -> None:
        """collector.yaml 파일이 올바르게 로드되는지 확인."""
        config = load_config("collector")
        
        assert isinstance(config, CollectorConfig)
        assert config.ftp_host == "ftp.3gpp.org"
        assert len(config.targets) == 3
        assert config.max_retry == 3
        assert config.retry_delay == 5

    def test_collector_targets(self) -> None:
        """수집 대상 TSG 설정이 올바르게 로드되는지 확인."""
        config = load_config("collector")
        
        tsg_names = [t.tsg for t in config.targets]
        assert "RAN" in tsg_names
        assert "SA" in tsg_names
        assert "CT" in tsg_names

    def test_collector_target_structure(self) -> None:
        """각 수집 대상의 구조가 올바른지 확인."""
        config = load_config("collector")
        
        for target in config.targets:
            assert isinstance(target, CollectorTarget)
            assert isinstance(target.tsg, str)
            assert isinstance(target.min_meeting, int)
            assert isinstance(target.wg_list, list)
            assert target.min_meeting >= 69
            assert len(target.wg_list) > 0

    def test_collector_wg_list_content(self) -> None:
        """WG 목록이 올바른 항목을 포함하는지 확인."""
        config = load_config("collector")
        
        for target in config.targets:
            assert "TSG" in target.wg_list
            assert "WG1" in target.wg_list


class TestLoadPreprocessingConfig:
    """Preprocessing 설정 로드 테스트."""

    def test_load_preprocessing_config(self) -> None:
        """preprocessing.yaml 파일이 올바르게 로드되는지 확인."""
        config = load_config("preprocessing")
        
        assert isinstance(config, PreprocessingConfig)
        assert len(config.title_exclude_patterns) > 0
        assert isinstance(config.source_cleaning, SourceCleaningConfig)
        assert isinstance(config.membership_normalization, NormalizationConfig)
        assert isinstance(config.date_range, DateRange)

    def test_title_exclude_patterns(self) -> None:
        """Title 제외 패턴이 올바르게 로드되는지 확인."""
        config = load_config("preprocessing")
        
        # 12개 LS 패턴 + CR pack = 13개
        assert len(config.title_exclude_patterns) == 13
        assert "LS on" in config.title_exclude_patterns
        assert "CR pack" in config.title_exclude_patterns

    def test_source_cleaning_config(self) -> None:
        """Source 정제 설정이 올바르게 로드되는지 확인."""
        config = load_config("preprocessing")
        sc = config.source_cleaning
        
        assert "CMCC" in sc.special_replacements
        assert sc.special_replacements["CMCC"] == "China Mobile"
        assert "[" in sc.remove_characters
        assert "]" in sc.remove_characters
        assert "." in sc.remove_characters
        assert sc.add_word_boundary_spaces is True

    def test_membership_normalization_stopwords(self) -> None:
        """멤버십 정규화 stopwords가 올바르게 로드되는지 확인 (62개)."""
        config = load_config("preprocessing")
        norm = config.membership_normalization
        
        # 법인격 47개 + 일반 단어 15개 = 62개
        assert len(norm.stopwords) == 62
        assert " GmbH" in norm.stopwords
        assert " Ltd." in norm.stopwords
        assert " Technology" in norm.stopwords

    def test_membership_normalization_countries(self) -> None:
        """멤버십 정규화 countries가 올바르게 로드되는지 확인 (23개)."""
        config = load_config("preprocessing")
        norm = config.membership_normalization
        
        assert len(norm.countries) == 23
        assert " Germany" in norm.countries
        assert " Korea" in norm.countries

    def test_membership_normalization_removes(self) -> None:
        """멤버십 정규화 removes가 올바르게 로드되는지 확인 (4개)."""
        config = load_config("preprocessing")
        norm = config.membership_normalization
        
        assert len(norm.removes) == 4
        assert "Beijing" in norm.removes
        assert "Nanjing" in norm.removes

    def test_membership_normalization_replaces(self) -> None:
        """멤버십 정규화 replaces가 올바르게 로드되는지 확인 (15개)."""
        config = load_config("preprocessing")
        norm = config.membership_normalization
        
        assert len(norm.replaces) == 15
        assert norm.replaces.get("Guangdong OPPO") == "OPPO"
        assert norm.replaces.get("HuaWei") == "Huawei"

    def test_membership_normalization_suffix(self) -> None:
        """멤버십 정규화 suffix가 올바르게 로드되는지 확인 (54개)."""
        config = load_config("preprocessing")
        norm = config.membership_normalization
        
        assert len(norm.suffix) == 54
        assert " Software" in norm.suffix
        assert " Research" in norm.suffix

    def test_membership_normalization_prefix(self) -> None:
        """멤버십 정규화 prefix가 올바르게 로드되는지 확인 (8개)."""
        config = load_config("preprocessing")
        norm = config.membership_normalization
        
        assert len(norm.prefix) == 8
        assert "Hangzhou " in norm.prefix
        assert "Shanghai " in norm.prefix

    def test_wi_settings(self) -> None:
        """Work Item 설정이 올바르게 로드되는지 확인."""
        config = load_config("preprocessing")
        
        assert "," in config.wi_delimiters
        assert "TEI" in config.wi_exclude_patterns
        assert "DUMMY" in config.wi_exclude_patterns

    def test_date_range(self) -> None:
        """날짜 범위 설정이 올바르게 로드되는지 확인."""
        config = load_config("preprocessing")
        
        assert config.date_range.min_year == 2015


class TestLoadNetworkConfig:
    """Network 설정 로드 테스트."""

    def test_load_network_config(self) -> None:
        """network.yaml 파일이 올바르게 로드되는지 확인."""
        config = load_config("network")
        
        assert isinstance(config, NetworkConfig)
        assert len(config.thresholds) == 10
        assert config.thresholds == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

    def test_time_units(self) -> None:
        """시간 단위 설정이 올바르게 로드되는지 확인."""
        config = load_config("network")
        
        assert "year" in config.time_units
        assert "release" in config.time_units
        assert "quarter" in config.time_units

    def test_tsg_groups(self) -> None:
        """TSG 그룹 설정이 올바르게 로드되는지 확인."""
        config = load_config("network")
        
        assert "ALL" in config.tsg_groups
        assert "RAN" in config.tsg_groups
        assert "SA" in config.tsg_groups
        assert "CT" in config.tsg_groups


class TestLoadAnalysisConfig:
    """Analysis 설정 로드 테스트."""

    def test_load_analysis_config(self) -> None:
        """analysis.yaml 파일이 올바르게 로드되는지 확인."""
        config = load_config("analysis")
        
        assert isinstance(config, AnalysisConfig)
        assert config.louvain_seed == 42
        assert config.eigenvector_max_iter == 1000
        assert config.random_network_samples == 100


class TestLoadPipelineConfig:
    """Pipeline 설정 로드 테스트."""

    def test_load_pipeline_config(self) -> None:
        """pipeline.yaml 파일이 올바르게 로드되는지 확인."""
        config = load_config("pipeline")
        
        assert isinstance(config, PipelineConfig)
        assert config.schedule == "0 0 * * 0"


class TestLoadConfigFunction:
    """load_config 편의 함수 테스트."""

    def test_load_config_with_extension(self) -> None:
        """확장자 포함 파일명으로 로드가 되는지 확인."""
        config = load_config("collector.yaml")
        assert isinstance(config, CollectorConfig)

    def test_load_config_without_extension(self) -> None:
        """확장자 없이 파일명으로 로드가 되는지 확인."""
        config = load_config("collector")
        assert isinstance(config, CollectorConfig)

    def test_load_config_invalid_name(self) -> None:
        """잘못된 설정 파일명에 대해 ValueError가 발생하는지 확인."""
        with pytest.raises(ValueError, match="지원하지 않는 설정 파일"):
            load_config("invalid_config")


class TestLoadRawYaml:
    """load_raw_yaml 함수 테스트."""

    def test_load_raw_yaml_returns_dict(self) -> None:
        """딕셔너리가 반환되는지 확인."""
        data = load_raw_yaml("collector")
        assert isinstance(data, dict)

    def test_load_raw_yaml_with_extension(self) -> None:
        """확장자 포함 파일명으로 로드가 되는지 확인."""
        data = load_raw_yaml("collector.yaml")
        assert isinstance(data, dict)
        assert "ftp" in data


class TestConfigLoaderWithMockFiles:
    """임시 설정 파일을 사용한 ConfigLoader 테스트."""

    def test_file_not_found(self, tmp_path: Path) -> None:
        """존재하지 않는 파일 로드 시 FileNotFoundError가 발생하는지 확인."""
        loader = ConfigLoader(config_dir=tmp_path)
        
        with pytest.raises(FileNotFoundError):
            loader._load_yaml("nonexistent.yaml")

    def test_custom_collector_config(self, tmp_path: Path) -> None:
        """커스텀 collector.yaml 로드 테스트."""
        config_content = {
            "ftp": {
                "host": "test.ftp.org",
                "base_path_template": "/test/{tsg}/",
            },
            "targets": [
                {"tsg": "TEST", "min_meeting": 100, "wg_list": ["WG1"]}
            ],
            "retry": {
                "max_attempts": 5,
                "delay_seconds": 10,
            },
        }
        
        config_file = tmp_path / "collector.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_content, f)
        
        loader = ConfigLoader(config_dir=tmp_path)
        config = loader.load_collector_config()
        
        assert config.ftp_host == "test.ftp.org"
        assert len(config.targets) == 1
        assert config.targets[0].tsg == "TEST"
        assert config.max_retry == 5


class TestConfigDataclassProperties:
    """Config dataclass 속성 테스트."""

    def test_collector_target_dataclass(self) -> None:
        """CollectorTarget dataclass 생성 테스트."""
        target = CollectorTarget(
            tsg="RAN",
            min_meeting=69,
            wg_list=["TSG", "WG1", "WG2"],
        )
        
        assert target.tsg == "RAN"
        assert target.min_meeting == 69
        assert len(target.wg_list) == 3

    def test_source_cleaning_config_dataclass(self) -> None:
        """SourceCleaningConfig dataclass 생성 테스트."""
        config = SourceCleaningConfig(
            special_replacements={"CMCC": "China Mobile"},
            remove_characters=["[", "]"],
            add_word_boundary_spaces=True,
        )
        
        assert config.special_replacements["CMCC"] == "China Mobile"
        assert len(config.remove_characters) == 2
        assert config.add_word_boundary_spaces is True

    def test_normalization_config_dataclass(self) -> None:
        """NormalizationConfig dataclass 생성 테스트."""
        config = NormalizationConfig(
            stopwords=[" Ltd.", " Inc."],
            countries=[" USA", " Korea"],
            removes=["Beijing"],
            replaces={"HuaWei": "Huawei"},
            brackets_pattern=r"\s\(",
            startswith_exceptions=["BTL"],
            suffix=[" Software"],
            prefix=["Shanghai "],
        )
        
        assert len(config.stopwords) == 2
        assert len(config.countries) == 2
        assert len(config.removes) == 1
        assert config.replaces["HuaWei"] == "Huawei"

    def test_date_range_dataclass(self) -> None:
        """DateRange dataclass 생성 테스트."""
        dr = DateRange(min_year=2015)
        assert dr.min_year == 2015


class TestConfigIntegration:
    """설정 통합 테스트."""

    def test_all_configs_loadable(self) -> None:
        """모든 설정 파일이 로드 가능한지 확인."""
        configs = ["collector", "preprocessing", "network", "analysis", "pipeline"]
        
        for config_name in configs:
            config = load_config(config_name)
            assert config is not None, f"{config_name} 설정 로드 실패"

    def test_preprocessing_normalization_counts(self) -> None:
        """멤버십 정규화 규칙 개수가 요구사항과 일치하는지 확인.
        
        2026-09 원본 노트북 재검증 결과 기준:
        - stopwords: 법인격(47) + 일반 단어(15) = 62개
        - countries: 23개
        - removes: 4개
        - replaces: 15개
        - startswith_exceptions: 4개
        - suffix: 54개
        - prefix: 8개
        """
        config = load_config("preprocessing")
        norm = config.membership_normalization
        
        assert len(norm.stopwords) == 62, f"stopwords 개수 불일치: {len(norm.stopwords)}"
        assert len(norm.countries) == 23, f"countries 개수 불일치: {len(norm.countries)}"
        assert len(norm.removes) == 4, f"removes 개수 불일치: {len(norm.removes)}"
        assert len(norm.replaces) == 15, f"replaces 개수 불일치: {len(norm.replaces)}"
        assert len(norm.startswith_exceptions) == 4, f"startswith_exceptions 개수 불일치: {len(norm.startswith_exceptions)}"
        assert len(norm.suffix) == 54, f"suffix 개수 불일치: {len(norm.suffix)}"
        assert len(norm.prefix) == 8, f"prefix 개수 불일치: {len(norm.prefix)}"



# =============================================================================
# Property-based Tests with Hypothesis
# =============================================================================


class TestConfigLoaderPropertyBased:
    """ConfigLoader Property-based 테스트 (Hypothesis 사용).
    
    YAML 로드 및 dataclass 변환의 universal properties를 검증합니다.
    
    **Validates: Requirements 17.1, 17.2**
    """

    @given(
        host=st.text(min_size=1, max_size=50).filter(lambda x: "\n" not in x and ":" not in x),
        max_retry=st.integers(min_value=1, max_value=100),
        delay=st.integers(min_value=1, max_value=300),
    )
    @settings(max_examples=50, deadline=None)
    def test_collector_config_roundtrip(
        self, host: str, max_retry: int, delay: int
    ) -> None:
        """Property: CollectorConfig는 YAML로 저장 후 로드해도 값이 보존된다.
        
        YAML로 저장한 Collector 설정을 다시 로드했을 때,
        원본 값과 동일한 값이 반환되어야 한다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        # YAML 호환성을 위해 문자열 정리
        host = host.strip() or "test.host"
        
        config_content = {
            "ftp": {
                "host": host,
                "base_path_template": "/test/{tsg}/",
            },
            "targets": [
                {"tsg": "RAN", "min_meeting": 69, "wg_list": ["TSG", "WG1"]}
            ],
            "retry": {
                "max_attempts": max_retry,
                "delay_seconds": delay,
            },
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_file = tmp_path / "collector.yaml"
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_content, f, allow_unicode=True)

            loader = ConfigLoader(config_dir=tmp_path)
            loaded_config = loader.load_collector_config()

            assert loaded_config.ftp_host == host
            assert loaded_config.max_retry == max_retry
            assert loaded_config.retry_delay == delay

    @given(
        patterns=st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P"),  # 문자, 숫자, 구두점만
                    blacklist_characters="\n\r\x85\u2028\u2029",  # YAML 줄바꿈 문자 제외
                ),
                min_size=1,
                max_size=30,
            ),
            min_size=0,
            max_size=20,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_preprocessing_title_patterns_roundtrip(self, patterns: List[str]) -> None:
        """Property: title_exclude_patterns는 YAML 저장/로드 후 순서와 값이 보존된다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        config_content = {
            "title_exclude_patterns": patterns,
            "source_cleaning": {
                "special_replacements": {},
                "remove_characters": [],
                "add_word_boundary_spaces": True,
            },
            "membership_normalization": {
                "stopwords": [],
                "countries": [],
                "removes": [],
                "replaces": {},
                "brackets_pattern": r"\s\(",
                "startswith_exceptions": [],
                "suffix": [],
                "prefix": [],
            },
            "wi_delimiters": [","],
            "wi_exclude_patterns": [],
            "date_range": {"min_year": 2015},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_file = tmp_path / "preprocessing.yaml"
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_content, f, allow_unicode=True)

            loader = ConfigLoader(config_dir=tmp_path)
            loaded_config = loader.load_preprocessing_config()

            assert loaded_config.title_exclude_patterns == patterns

    @given(
        thresholds=st.lists(
            st.integers(min_value=0, max_value=100),
            min_size=1,
            max_size=20,
        ),
        time_units=st.lists(
            st.sampled_from(["year", "release", "quarter", "month"]),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_network_config_roundtrip(
        self, thresholds: List[int], time_units: List[str]
    ) -> None:
        """Property: NetworkConfig의 thresholds와 time_units는 순서가 보존된다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        config_content = {
            "thresholds": thresholds,
            "time_units": time_units,
            "tsg_groups": ["ALL", "RAN", "SA", "CT"],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_file = tmp_path / "network.yaml"
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_content, f)

            loader = ConfigLoader(config_dir=tmp_path)
            loaded_config = loader.load_network_config()

            assert loaded_config.thresholds == thresholds
            assert loaded_config.time_units == time_units

    @given(
        seed=st.integers(min_value=0, max_value=2**31 - 1),
        max_iter=st.integers(min_value=100, max_value=10000),
        samples=st.integers(min_value=10, max_value=1000),
    )
    @settings(max_examples=50, deadline=None)
    def test_analysis_config_roundtrip(
        self, seed: int, max_iter: int, samples: int
    ) -> None:
        """Property: AnalysisConfig 숫자 파라미터는 정확히 보존된다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        config_content = {
            "louvain_seed": seed,
            "eigenvector_max_iter": max_iter,
            "random_network_samples": samples,
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_file = tmp_path / "analysis.yaml"
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_content, f)

            loader = ConfigLoader(config_dir=tmp_path)
            loaded_config = loader.load_analysis_config()

            assert loaded_config.louvain_seed == seed
            assert loaded_config.eigenvector_max_iter == max_iter
            assert loaded_config.random_network_samples == samples


class TestNormalizationConfigPropertyBased:
    """NormalizationConfig 정규화 규칙 Property-based 테스트.
    
    멤버십 정규화 설정의 구조적 속성을 검증합니다.
    
    **Validates: Requirements 17.1, 17.2**
    """

    @given(
        stopwords=st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P"),
                    blacklist_characters="\n\r\x85\u2028\u2029",
                ),
                min_size=1,
                max_size=30,
            ),
            min_size=0,
            max_size=100,
        ),
        countries=st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P"),
                    blacklist_characters="\n\r\x85\u2028\u2029",
                ),
                min_size=1,
                max_size=30,
            ),
            min_size=0,
            max_size=50,
        ),
        suffix=st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P"),
                    blacklist_characters="\n\r\x85\u2028\u2029",
                ),
                min_size=1,
                max_size=30,
            ),
            min_size=0,
            max_size=100,
        ),
        prefix=st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P"),
                    blacklist_characters="\n\r\x85\u2028\u2029",
                ),
                min_size=1,
                max_size=30,
            ),
            min_size=0,
            max_size=30,
        ),
    )
    @settings(max_examples=30, deadline=None)
    def test_normalization_lists_length_preserved(
        self,
        stopwords: List[str],
        countries: List[str],
        suffix: List[str],
        prefix: List[str],
    ) -> None:
        """Property: 정규화 리스트들의 길이가 저장/로드 후 보존된다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        config_content = {
            "title_exclude_patterns": [],
            "source_cleaning": {
                "special_replacements": {},
                "remove_characters": [],
                "add_word_boundary_spaces": True,
            },
            "membership_normalization": {
                "stopwords": stopwords,
                "countries": countries,
                "removes": [],
                "replaces": {},
                "brackets_pattern": r"\s\(",
                "startswith_exceptions": [],
                "suffix": suffix,
                "prefix": prefix,
            },
            "wi_delimiters": [","],
            "wi_exclude_patterns": [],
            "date_range": {"min_year": 2015},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_file = tmp_path / "preprocessing.yaml"
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_content, f, allow_unicode=True)

            loader = ConfigLoader(config_dir=tmp_path)
            loaded = loader.load_preprocessing_config()
            norm = loaded.membership_normalization

            assert len(norm.stopwords) == len(stopwords)
            assert len(norm.countries) == len(countries)
            assert len(norm.suffix) == len(suffix)
            assert len(norm.prefix) == len(prefix)

    @given(
        replaces=st.dictionaries(
            keys=st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N"),
                    blacklist_characters="\n\r\x85\u2028\u2029",
                ),
                min_size=1,
                max_size=30,
            ),
            values=st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P"),
                    blacklist_characters="\n\r\x85\u2028\u2029",
                ),
                min_size=1,
                max_size=30,
            ),
            min_size=0,
            max_size=30,
        )
    )
    @settings(max_examples=30, deadline=None)
    def test_normalization_replaces_dict_preserved(self, replaces: Dict[str, str]) -> None:
        """Property: replaces 딕셔너리의 key-value 쌍이 보존된다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        config_content = {
            "title_exclude_patterns": [],
            "source_cleaning": {
                "special_replacements": {},
                "remove_characters": [],
                "add_word_boundary_spaces": True,
            },
            "membership_normalization": {
                "stopwords": [],
                "countries": [],
                "removes": [],
                "replaces": replaces,
                "brackets_pattern": r"\s\(",
                "startswith_exceptions": [],
                "suffix": [],
                "prefix": [],
            },
            "wi_delimiters": [","],
            "wi_exclude_patterns": [],
            "date_range": {"min_year": 2015},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_file = tmp_path / "preprocessing.yaml"
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_content, f, allow_unicode=True)

            loader = ConfigLoader(config_dir=tmp_path)
            loaded = loader.load_preprocessing_config()
            norm = loaded.membership_normalization

            assert norm.replaces == replaces


class TestSourceCleaningConfigPropertyBased:
    """SourceCleaningConfig Property-based 테스트.
    
    Source 정제 설정의 구조적 속성을 검증합니다.
    
    **Validates: Requirements 17.1, 17.2**
    """

    # YAML에서 안전하게 사용할 수 있는 문자 집합
    # YAML은 특정 유니코드 문자(\x85 등)를 공백으로 변환함
    safe_yaml_text = st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S"),  # 문자, 숫자, 구두점, 기호
            blacklist_characters="\n\r\x85\u2028\u2029",  # 줄바꿈 유니코드 제외
        ),
        min_size=1,
        max_size=20,
    )

    @given(
        special_replacements=st.dictionaries(
            keys=st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N"),
                    blacklist_characters="\n\r\x85\u2028\u2029",
                ),
                min_size=1,
                max_size=20,
            ),
            values=st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P"),
                    blacklist_characters="\n\r\x85\u2028\u2029",
                ),
                min_size=1,
                max_size=30,
            ),
            min_size=0,
            max_size=10,
        ),
        remove_chars=st.lists(
            st.text(
                alphabet=st.sampled_from(list("[].,-;:(){}!?@#$%^&*")),
                min_size=1,
                max_size=3,
            ),
            min_size=0,
            max_size=10,
        ),
        add_boundary=st.booleans(),
    )
    @settings(max_examples=30, deadline=None)
    def test_source_cleaning_config_roundtrip(
        self,
        special_replacements: Dict[str, str],
        remove_chars: List[str],
        add_boundary: bool,
    ) -> None:
        """Property: SourceCleaningConfig의 모든 필드가 정확히 보존된다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        config_content = {
            "title_exclude_patterns": [],
            "source_cleaning": {
                "special_replacements": special_replacements,
                "remove_characters": remove_chars,
                "add_word_boundary_spaces": add_boundary,
            },
            "membership_normalization": {
                "stopwords": [],
                "countries": [],
                "removes": [],
                "replaces": {},
                "brackets_pattern": r"\s\(",
                "startswith_exceptions": [],
                "suffix": [],
                "prefix": [],
            },
            "wi_delimiters": [","],
            "wi_exclude_patterns": [],
            "date_range": {"min_year": 2015},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_file = tmp_path / "preprocessing.yaml"
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_content, f, allow_unicode=True)

            loader = ConfigLoader(config_dir=tmp_path)
            loaded = loader.load_preprocessing_config()
            sc = loaded.source_cleaning

            assert sc.special_replacements == special_replacements
            assert sc.remove_characters == remove_chars
            assert sc.add_word_boundary_spaces == add_boundary


class TestDataclassCreationPropertyBased:
    """Dataclass 생성 Property-based 테스트.
    
    Config dataclass들의 생성자 속성을 검증합니다.
    
    **Validates: Requirements 17.1, 17.2**
    """

    @given(
        tsg=st.sampled_from(["RAN", "SA", "CT"]),
        min_meeting=st.integers(min_value=1, max_value=500),
        wg_list=st.lists(
            st.sampled_from(["TSG", "WG1", "WG2", "WG3", "WG4", "WG5", "WG6"]),
            min_size=1,
            max_size=7,
            unique=True,
        ),
    )
    @settings(max_examples=50)
    def test_collector_target_creation(
        self, tsg: str, min_meeting: int, wg_list: List[str]
    ) -> None:
        """Property: CollectorTarget은 유효한 입력으로 항상 생성 가능하다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        target = CollectorTarget(
            tsg=tsg,
            min_meeting=min_meeting,
            wg_list=wg_list,
        )

        assert target.tsg == tsg
        assert target.min_meeting == min_meeting
        assert target.wg_list == wg_list
        assert len(target.wg_list) == len(wg_list)

    @given(min_year=st.integers(min_value=1990, max_value=2100))
    @settings(max_examples=50)
    def test_date_range_creation(self, min_year: int) -> None:
        """Property: DateRange는 유효한 연도로 항상 생성 가능하다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        dr = DateRange(min_year=min_year)
        assert dr.min_year == min_year

    @given(
        host=st.text(min_size=1, max_size=100),
        base_path=st.text(min_size=1, max_size=200),
        max_retry=st.integers(min_value=0, max_value=100),
        retry_delay=st.integers(min_value=0, max_value=600),
    )
    @settings(max_examples=50)
    def test_collector_config_creation(
        self, host: str, base_path: str, max_retry: int, retry_delay: int
    ) -> None:
        """Property: CollectorConfig는 유효한 입력으로 항상 생성 가능하다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        config = CollectorConfig(
            ftp_host=host,
            ftp_base_path_template=base_path,
            targets=[],
            max_retry=max_retry,
            retry_delay=retry_delay,
        )

        assert config.ftp_host == host
        assert config.ftp_base_path_template == base_path
        assert config.max_retry == max_retry
        assert config.retry_delay == retry_delay

    @given(
        seed=st.integers(min_value=0, max_value=2**31 - 1),
        max_iter=st.integers(min_value=1, max_value=100000),
        samples=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=50)
    def test_analysis_config_creation(
        self, seed: int, max_iter: int, samples: int
    ) -> None:
        """Property: AnalysisConfig는 유효한 숫자로 항상 생성 가능하다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        config = AnalysisConfig(
            louvain_seed=seed,
            eigenvector_max_iter=max_iter,
            random_network_samples=samples,
        )

        assert config.louvain_seed == seed
        assert config.eigenvector_max_iter == max_iter
        assert config.random_network_samples == samples


class TestConfigLoaderIdempotency:
    """Config Loader 멱등성(Idempotency) Property-based 테스트.
    
    **Validates: Requirements 17.1, 17.2**
    """

    def test_collector_config_load_idempotent(self) -> None:
        """Property: 동일한 collector.yaml을 여러 번 로드해도 결과가 동일하다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        loader = ConfigLoader()
        
        config1 = loader.load_collector_config()
        config2 = loader.load_collector_config()
        config3 = loader.load_collector_config()

        # 모든 필드가 동일해야 함
        assert config1.ftp_host == config2.ftp_host == config3.ftp_host
        assert config1.max_retry == config2.max_retry == config3.max_retry
        assert config1.retry_delay == config2.retry_delay == config3.retry_delay
        assert len(config1.targets) == len(config2.targets) == len(config3.targets)

    def test_preprocessing_config_load_idempotent(self) -> None:
        """Property: 동일한 preprocessing.yaml을 여러 번 로드해도 결과가 동일하다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        loader = ConfigLoader()
        
        config1 = loader.load_preprocessing_config()
        config2 = loader.load_preprocessing_config()

        assert config1.title_exclude_patterns == config2.title_exclude_patterns
        assert config1.wi_delimiters == config2.wi_delimiters
        assert config1.wi_exclude_patterns == config2.wi_exclude_patterns
        assert config1.date_range.min_year == config2.date_range.min_year
        
        # 중첩된 config도 동일해야 함
        norm1 = config1.membership_normalization
        norm2 = config2.membership_normalization
        assert norm1.stopwords == norm2.stopwords
        assert norm1.countries == norm2.countries
        assert norm1.replaces == norm2.replaces

    @given(config_name=st.sampled_from(["collector", "preprocessing", "network", "analysis", "pipeline"]))
    @settings(max_examples=10)
    def test_load_config_function_idempotent(self, config_name: str) -> None:
        """Property: load_config 함수는 동일한 설정에 대해 동일한 타입을 반환한다.
        
        **Validates: Requirements 17.1, 17.2**
        """
        config1 = load_config(config_name)
        config2 = load_config(config_name)

        assert type(config1) == type(config2)
