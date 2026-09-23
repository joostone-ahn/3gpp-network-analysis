"""
CacheManager 모듈 Property 테스트

캐시 무효화 정확성 테스트 (Property 14):
- 요구사항 7.2: 입력 파일의 수정 시각이 변경되지 않은 경우, 재실행 시 전처리 단계를 건너뛰고 캐시를 재사용

Property 14: 캐시 무효화 정확성
*For any* 입력 파일 집합에 대해, 파일의 수정 시각이 변경되지 않으면 캐시를 재사용하고,
하나라도 변경되면 캐시를 무효화해야 한다.

**Validates: Requirements 7.2, 17.1**
"""

import os
import pickle
import tempfile
import time
from pathlib import Path
from typing import Any, List, Tuple
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import assume, given, settings, HealthCheck
from hypothesis import strategies as st

from src.utils.cache_manager import (
    CacheInfo,
    CacheManager,
    CacheMetadata,
    get_cache_manager,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """임시 캐시 디렉토리 생성."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    return cache_dir


@pytest.fixture
def cache_manager(tmp_cache_dir: Path) -> CacheManager:
    """테스트용 CacheManager 인스턴스."""
    return CacheManager(cache_dir=tmp_cache_dir)


@pytest.fixture
def sample_input_files(tmp_path: Path) -> List[Path]:
    """테스트용 입력 파일 생성.
    
    수정 시각이 서로 다른 3개의 파일을 생성한다.
    """
    files = []
    for i in range(3):
        file_path = tmp_path / f"input_file_{i}.txt"
        file_path.write_text(f"content_{i}")
        files.append(file_path)
        # 파일별로 서로 다른 mtime을 가지도록 약간의 지연
        time.sleep(0.01)
    return files


# =============================================================================
# Unit Tests: CacheMetadata
# =============================================================================


class TestCacheMetadata:
    """CacheMetadata dataclass 테스트."""
    
    def test_metadata_creation(self):
        """CacheMetadata 객체 생성 테스트."""
        metadata = CacheMetadata(
            cache_key="test_key_123",
            created_at="2024-01-15T10:30:00",
            input_files=[
                {"path": "/test/file1.txt", "mtime": 1705312200.0, "size_bytes": 1024},
                {"path": "/test/file2.txt", "mtime": 1705312300.0, "size_bytes": 2048},
            ],
            description="Test cache metadata",
        )
        
        assert metadata.cache_key == "test_key_123"
        assert metadata.created_at == "2024-01-15T10:30:00"
        assert len(metadata.input_files) == 2
        assert metadata.description == "Test cache metadata"
    
    def test_metadata_default_values(self):
        """CacheMetadata 기본값 테스트."""
        metadata = CacheMetadata(
            cache_key="test_key",
            created_at="2024-01-15T10:30:00",
        )
        
        assert metadata.input_files == []
        assert metadata.description is None


class TestCacheInfo:
    """CacheInfo dataclass 테스트."""
    
    def test_cache_info_creation(self):
        """CacheInfo 객체 생성 테스트."""
        from datetime import datetime
        
        info = CacheInfo(
            total_files=10,
            total_size_bytes=1024000,
            oldest_file="cache_old.pkl",
            oldest_mtime=datetime(2024, 1, 1, 10, 0, 0),
            newest_file="cache_new.pkl",
            newest_mtime=datetime(2024, 1, 15, 10, 0, 0),
        )
        
        assert info.total_files == 10
        assert info.total_size_bytes == 1024000
        assert info.oldest_file == "cache_old.pkl"
        assert info.newest_file == "cache_new.pkl"
    
    def test_cache_info_default_values(self):
        """CacheInfo 기본값 테스트."""
        info = CacheInfo(
            total_files=0,
            total_size_bytes=0,
        )
        
        assert info.oldest_file is None
        assert info.oldest_mtime is None
        assert info.newest_file is None
        assert info.newest_mtime is None


# =============================================================================
# Unit Tests: CacheManager
# =============================================================================


class TestCacheManagerInit:
    """CacheManager 초기화 테스트."""
    
    def test_init_creates_directory(self, tmp_path: Path):
        """초기화 시 캐시 디렉토리가 생성되는지 테스트."""
        cache_dir = tmp_path / "new_cache_dir"
        assert not cache_dir.exists()
        
        manager = CacheManager(cache_dir=cache_dir)
        
        assert cache_dir.exists()
        assert cache_dir.is_dir()
    
    def test_init_with_existing_directory(self, tmp_cache_dir: Path):
        """기존 디렉토리로 초기화 테스트."""
        manager = CacheManager(cache_dir=tmp_cache_dir)
        
        assert manager.cache_dir == tmp_cache_dir
    
    def test_init_with_string_path(self, tmp_path: Path):
        """문자열 경로로 초기화 테스트."""
        cache_dir = str(tmp_path / "string_cache")
        
        manager = CacheManager(cache_dir=cache_dir)
        
        assert manager.cache_dir == Path(cache_dir)
        assert manager.cache_dir.exists()


class TestCacheManagerGetCacheKey:
    """CacheManager.get_cache_key() 테스트."""
    
    def test_get_cache_key_basic(self, cache_manager: CacheManager, sample_input_files: List[Path]):
        """기본 캐시 키 생성 테스트."""
        cache_key = cache_manager.get_cache_key(sample_input_files)
        
        # SHA-256 해시는 64자
        assert len(cache_key) == 64
        assert all(c in "0123456789abcdef" for c in cache_key)
    
    def test_get_cache_key_deterministic(
        self, cache_manager: CacheManager, sample_input_files: List[Path]
    ):
        """동일 파일에 대해 동일 캐시 키 생성 테스트."""
        key1 = cache_manager.get_cache_key(sample_input_files)
        key2 = cache_manager.get_cache_key(sample_input_files)
        
        assert key1 == key2
    
    def test_get_cache_key_order_independent(
        self, cache_manager: CacheManager, sample_input_files: List[Path]
    ):
        """파일 순서에 무관하게 동일 캐시 키 생성 테스트."""
        key1 = cache_manager.get_cache_key(sample_input_files)
        key2 = cache_manager.get_cache_key(list(reversed(sample_input_files)))
        
        assert key1 == key2
    
    def test_get_cache_key_different_files(
        self, cache_manager: CacheManager, sample_input_files: List[Path], tmp_path: Path
    ):
        """서로 다른 파일에 대해 서로 다른 캐시 키 생성 테스트."""
        # 추가 파일 생성
        extra_file = tmp_path / "extra_file.txt"
        extra_file.write_text("extra_content")
        
        key1 = cache_manager.get_cache_key(sample_input_files)
        key2 = cache_manager.get_cache_key(sample_input_files + [extra_file])
        
        assert key1 != key2
    
    def test_get_cache_key_mtime_sensitive(
        self, cache_manager: CacheManager, sample_input_files: List[Path]
    ):
        """파일 mtime 변경 시 캐시 키 변경 테스트 (Property 14 핵심)."""
        key1 = cache_manager.get_cache_key(sample_input_files)
        
        # 첫 번째 파일의 mtime 변경 (내용 수정)
        time.sleep(0.01)  # mtime 변경을 보장하기 위한 지연
        sample_input_files[0].write_text("modified_content")
        
        key2 = cache_manager.get_cache_key(sample_input_files)
        
        assert key1 != key2
    
    def test_get_cache_key_empty_list(self, cache_manager: CacheManager):
        """빈 파일 리스트에 대한 캐시 키 생성 테스트."""
        cache_key = cache_manager.get_cache_key([])
        
        # 빈 리스트도 고유한 해시 반환
        assert len(cache_key) == 64
        assert cache_key == cache_manager.get_cache_key([])  # 재현성
    
    def test_get_cache_key_file_not_found(self, cache_manager: CacheManager):
        """존재하지 않는 파일에 대한 에러 처리 테스트."""
        non_existent = Path("/non/existent/file.txt")
        
        with pytest.raises(FileNotFoundError):
            cache_manager.get_cache_key([non_existent])
    
    def test_get_cache_key_string_paths(
        self, cache_manager: CacheManager, sample_input_files: List[Path]
    ):
        """문자열 경로도 처리 가능한지 테스트."""
        path_key = cache_manager.get_cache_key(sample_input_files)
        string_key = cache_manager.get_cache_key([str(f) for f in sample_input_files])
        
        assert path_key == string_key


class TestCacheManagerIsValid:
    """CacheManager.is_valid() 테스트."""
    
    def test_is_valid_existing_cache(self, cache_manager: CacheManager):
        """존재하는 캐시에 대한 유효성 검증 테스트."""
        cache_key = "test_cache_key"
        
        # 캐시 파일 직접 생성
        cache_file = cache_manager._get_cache_file_path(cache_key)
        cache_file.write_bytes(pickle.dumps({"data": "test"}))
        
        assert cache_manager.is_valid(cache_key) is True
    
    def test_is_valid_non_existing_cache(self, cache_manager: CacheManager):
        """존재하지 않는 캐시에 대한 유효성 검증 테스트."""
        cache_key = "non_existing_cache_key"
        
        assert cache_manager.is_valid(cache_key) is False


class TestCacheManagerSaveLoad:
    """CacheManager.save() / load() 테스트."""
    
    def test_save_and_load_basic(self, cache_manager: CacheManager):
        """기본 저장/로드 테스트."""
        cache_key = "test_save_load"
        data = {"key": "value", "list": [1, 2, 3]}
        
        cache_manager.save(cache_key, data)
        loaded = cache_manager.load(cache_key)
        
        assert loaded == data
    
    def test_save_with_metadata(
        self, cache_manager: CacheManager, sample_input_files: List[Path]
    ):
        """메타데이터와 함께 저장 테스트."""
        cache_key = "test_with_metadata"
        data = {"result": "test"}
        
        cache_manager.save(
            cache_key,
            data,
            input_files=sample_input_files,
            description="Test cache with metadata",
        )
        
        # 메타데이터 파일 존재 확인
        metadata_file = cache_manager._get_metadata_file_path(cache_key)
        assert metadata_file.exists()
    
    def test_load_non_existing(self, cache_manager: CacheManager):
        """존재하지 않는 캐시 로드 테스트."""
        result = cache_manager.load("non_existing_key")
        
        assert result is None
    
    def test_load_corrupted_cache(self, cache_manager: CacheManager):
        """손상된 캐시 파일 로드 테스트."""
        cache_key = "corrupted_cache"
        cache_file = cache_manager._get_cache_file_path(cache_key)
        
        # 손상된 파일 생성
        cache_file.write_bytes(b"corrupted data that is not pickle")
        
        result = cache_manager.load(cache_key)
        
        assert result is None
    
    def test_save_various_data_types(self, cache_manager: CacheManager):
        """다양한 데이터 타입 저장/로드 테스트."""
        test_cases = [
            ("string_data", "test string"),
            ("int_data", 12345),
            ("float_data", 3.14159),
            ("list_data", [1, 2, 3, "four", 5.0]),
            ("dict_data", {"a": 1, "b": {"c": 2}}),
            ("tuple_data", (1, 2, 3)),
            ("none_data", None),
            ("bool_data", True),
        ]
        
        for cache_key, data in test_cases:
            cache_manager.save(cache_key, data)
            loaded = cache_manager.load(cache_key)
            assert loaded == data, f"Failed for {cache_key}"


class TestCacheManagerClear:
    """CacheManager.clear() 테스트."""
    
    def test_clear_all(self, cache_manager: CacheManager):
        """전체 캐시 삭제 테스트."""
        # 여러 캐시 저장
        for i in range(5):
            cache_manager.save(f"cache_{i}", {"data": i})
        
        deleted_count = cache_manager.clear()
        
        # pkl 파일 5개 + json 파일 5개 = 10개
        assert deleted_count == 10
        
        # 모든 캐시 삭제 확인
        for i in range(5):
            assert not cache_manager.is_valid(f"cache_{i}")
    
    def test_clear_with_pattern(self, cache_manager: CacheManager):
        """패턴으로 캐시 삭제 테스트."""
        # 다양한 이름의 캐시 저장
        cache_manager.save("preprocessor_v1", {"data": 1})
        cache_manager.save("preprocessor_v2", {"data": 2})
        cache_manager.save("network_v1", {"data": 3})
        
        deleted_count = cache_manager.clear(pattern="preprocessor_*")
        
        # preprocessor_* 패턴에 맞는 파일만 삭제 (2개 * 2 = 4)
        assert deleted_count == 4
        
        # preprocessor 캐시 삭제 확인
        assert not cache_manager.is_valid("preprocessor_v1")
        assert not cache_manager.is_valid("preprocessor_v2")
        
        # network 캐시는 유지
        assert cache_manager.is_valid("network_v1")
    
    def test_clear_empty_cache(self, cache_manager: CacheManager):
        """빈 캐시 삭제 테스트."""
        deleted_count = cache_manager.clear()
        
        assert deleted_count == 0


class TestCacheManagerGetCacheInfo:
    """CacheManager.get_cache_info() 테스트."""
    
    def test_get_cache_info_empty(self, cache_manager: CacheManager):
        """빈 캐시 정보 테스트."""
        info = cache_manager.get_cache_info()
        
        assert info["total_files"] == 0
        assert info["total_size_bytes"] == 0
        assert info["oldest_file"] is None
        assert info["newest_file"] is None
    
    def test_get_cache_info_with_caches(self, cache_manager: CacheManager):
        """캐시가 있을 때 정보 테스트."""
        # 캐시 저장
        for i in range(3):
            cache_manager.save(f"cache_{i}", {"data": i})
            time.sleep(0.01)  # mtime 차이 보장
        
        info = cache_manager.get_cache_info()
        
        assert info["total_files"] == 3
        assert info["total_size_bytes"] > 0
        assert info["oldest_file"] is not None
        assert info["newest_file"] is not None
        assert info["cache_dir"] == str(cache_manager.cache_dir)


class TestCacheManagerGetOrCompute:
    """CacheManager.get_or_compute() 테스트."""
    
    def test_get_or_compute_cache_miss(
        self, cache_manager: CacheManager, sample_input_files: List[Path]
    ):
        """캐시 미스 시 계산 수행 테스트."""
        compute_fn = MagicMock(return_value={"computed": "result"})
        
        result = cache_manager.get_or_compute(
            input_files=sample_input_files,
            compute_fn=compute_fn,
            description="Test computation",
        )
        
        # 계산 함수가 호출됨
        compute_fn.assert_called_once()
        assert result == {"computed": "result"}
    
    def test_get_or_compute_cache_hit(
        self, cache_manager: CacheManager, sample_input_files: List[Path]
    ):
        """캐시 히트 시 계산 건너뛰기 테스트 (Property 14 핵심)."""
        compute_fn = MagicMock(return_value={"computed": "result"})
        
        # 첫 번째 호출: 캐시 미스, 계산 수행
        result1 = cache_manager.get_or_compute(
            input_files=sample_input_files,
            compute_fn=compute_fn,
        )
        
        # 두 번째 호출: 캐시 히트, 계산 건너뛰기
        result2 = cache_manager.get_or_compute(
            input_files=sample_input_files,
            compute_fn=compute_fn,
        )
        
        # 계산 함수는 한 번만 호출됨
        assert compute_fn.call_count == 1
        assert result1 == result2
    
    def test_get_or_compute_cache_invalidation(
        self, cache_manager: CacheManager, sample_input_files: List[Path]
    ):
        """파일 변경 시 캐시 무효화 및 재계산 테스트 (Property 14 핵심)."""
        call_count = 0
        
        def compute_fn():
            nonlocal call_count
            call_count += 1
            return {"computed": call_count}
        
        # 첫 번째 호출: 캐시 미스
        result1 = cache_manager.get_or_compute(
            input_files=sample_input_files,
            compute_fn=compute_fn,
        )
        assert result1 == {"computed": 1}
        
        # 파일 수정 (mtime 변경)
        time.sleep(0.01)
        sample_input_files[0].write_text("modified_content_for_test")
        
        # 두 번째 호출: 캐시 무효화로 재계산
        result2 = cache_manager.get_or_compute(
            input_files=sample_input_files,
            compute_fn=compute_fn,
        )
        
        # 계산 함수가 두 번 호출됨 (캐시 무효화 확인)
        assert call_count == 2
        assert result2 == {"computed": 2}


# =============================================================================
# Property-Based Tests (Hypothesis)
# =============================================================================


class TestCacheInvalidationProperty:
    """Property 14: 캐시 무효화 정확성 테스트 (Property-Based Testing).
    
    **Validates: Requirements 7.2**
    
    *For any* 입력 파일 집합에 대해, 파일의 수정 시각이 변경되지 않으면 캐시를 재사용하고,
    하나라도 변경되면 캐시를 무효화해야 한다.
    """
    
    @given(
        num_files=st.integers(min_value=1, max_value=10),
        mtime_changes=st.lists(st.booleans(), min_size=1, max_size=10),
    )
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_cache_invalidation_on_mtime_change(
        self, num_files: int, mtime_changes: List[bool]
    ):
        """파일 mtime 변경 시 캐시 무효화 property 테스트.
        
        Property: 어떤 파일의 mtime이라도 변경되면 캐시 키가 변경되어야 한다.
        
        **Validates: Requirements 7.2**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cache_dir = tmp_path / "cache"
            cache_dir.mkdir()
            
            # CacheManager 생성
            manager = CacheManager(cache_dir=cache_dir)
            
            # 입력 파일 생성
            files = []
            for i in range(num_files):
                file_path = tmp_path / f"file_{i}.txt"
                file_path.write_text(f"content_{i}")
                files.append(file_path)
            
            # 초기 캐시 키 계산
            cache_key_before = manager.get_cache_key(files)
            
            # mtime_changes 리스트를 파일 수에 맞게 조정
            changes_to_apply = mtime_changes[:num_files]
            
            # 변경 적용
            any_change = False
            for i, should_change in enumerate(changes_to_apply):
                if should_change and i < len(files):
                    any_change = True
                    time.sleep(0.01)  # mtime 변경 보장
                    files[i].write_text(f"modified_content_{i}")
            
            # 변경 후 캐시 키 계산
            cache_key_after = manager.get_cache_key(files)
            
            # Property 검증
            if any_change:
                # 어떤 파일이라도 변경되면 캐시 키가 달라져야 함
                assert cache_key_before != cache_key_after, \
                    "Cache key should change when any file mtime changes"
            else:
                # 변경이 없으면 캐시 키가 동일해야 함
                assert cache_key_before == cache_key_after, \
                    "Cache key should remain same when no file mtime changes"
    
    @given(
        file_contents=st.lists(
            st.text(min_size=1, max_size=100, alphabet=st.characters(
                whitelist_categories=('L', 'N', 'P', 'Z'),
                whitelist_characters=' '
            )),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_cache_key_determinism(self, file_contents: List[str]):
        """캐시 키 결정론적 생성 property 테스트.
        
        Property: 동일한 파일 집합에 대해 항상 동일한 캐시 키가 생성되어야 한다.
        
        **Validates: Requirements 7.2, 16.2**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cache_dir = tmp_path / "cache"
            cache_dir.mkdir()
            
            manager = CacheManager(cache_dir=cache_dir)
            
            # 입력 파일 생성
            files = []
            for i, content in enumerate(file_contents):
                file_path = tmp_path / f"file_{i}.txt"
                file_path.write_text(content)
                files.append(file_path)
            
            # 캐시 키를 여러 번 계산
            key1 = manager.get_cache_key(files)
            key2 = manager.get_cache_key(files)
            key3 = manager.get_cache_key(files)
            
            # 모두 동일해야 함
            assert key1 == key2 == key3, \
                "Cache key should be deterministic for same input"
    
    @given(
        file_contents=st.lists(
            st.text(min_size=1, max_size=50, alphabet=st.characters(
                whitelist_categories=('L', 'N'),
                whitelist_characters=' '
            )),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_cache_key_order_independence(self, file_contents: List[str]):
        """캐시 키 순서 독립성 property 테스트.
        
        Property: 파일 리스트의 순서에 관계없이 동일한 캐시 키가 생성되어야 한다.
        
        **Validates: Requirements 7.2**
        """
        assume(len(file_contents) >= 2)  # 순서 비교를 위해 최소 2개 필요
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cache_dir = tmp_path / "cache"
            cache_dir.mkdir()
            
            manager = CacheManager(cache_dir=cache_dir)
            
            # 입력 파일 생성
            files = []
            for i, content in enumerate(file_contents):
                file_path = tmp_path / f"file_{i}.txt"
                file_path.write_text(content)
                files.append(file_path)
            
            # 순서가 다른 리스트로 캐시 키 계산
            key_original = manager.get_cache_key(files)
            key_reversed = manager.get_cache_key(list(reversed(files)))
            
            # 순서와 무관하게 동일해야 함
            assert key_original == key_reversed, \
                "Cache key should be independent of file list order"
    
    @given(
        data_to_cache=st.one_of(
            st.dictionaries(
                keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L',))),
                values=st.integers(),
                min_size=0,
                max_size=10,
            ),
            st.lists(st.integers(), min_size=0, max_size=20),
            st.integers(),
            st.text(min_size=0, max_size=100),
        ),
    )
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_cache_roundtrip_property(self, data_to_cache: Any):
        """캐시 라운드트립 property 테스트.
        
        Property: 저장 후 로드한 데이터는 원본과 동일해야 한다.
        
        **Validates: Requirements 7.2, 17.3**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cache_dir = tmp_path / "cache"
            cache_dir.mkdir()
            
            manager = CacheManager(cache_dir=cache_dir)
            
            cache_key = "test_roundtrip"
            
            # 저장 및 로드
            manager.save(cache_key, data_to_cache)
            loaded = manager.load(cache_key)
            
            # 원본과 동일해야 함
            assert loaded == data_to_cache, \
                f"Loaded data should equal original: {data_to_cache} vs {loaded}"
    
    @given(
        num_files=st.integers(min_value=1, max_value=5),
    )
    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_get_or_compute_caching_property(self, num_files: int):
        """get_or_compute 캐싱 동작 property 테스트.
        
        Property: mtime이 변경되지 않으면 compute_fn은 한 번만 호출되어야 한다.
        
        **Validates: Requirements 7.2**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cache_dir = tmp_path / "cache"
            cache_dir.mkdir()
            
            manager = CacheManager(cache_dir=cache_dir)
            
            # 입력 파일 생성
            files = []
            for i in range(num_files):
                file_path = tmp_path / f"file_{i}.txt"
                file_path.write_text(f"content_{i}")
                files.append(file_path)
            
            call_count = 0
            
            def compute_fn():
                nonlocal call_count
                call_count += 1
                return {"computed": call_count}
            
            # 여러 번 호출
            result1 = manager.get_or_compute(files, compute_fn)
            result2 = manager.get_or_compute(files, compute_fn)
            result3 = manager.get_or_compute(files, compute_fn)
            
            # compute_fn은 한 번만 호출되어야 함
            assert call_count == 1, \
                f"compute_fn should be called once but was called {call_count} times"
            
            # 모든 결과가 동일해야 함
            assert result1 == result2 == result3, \
                "All results from get_or_compute should be equal"


class TestCacheKeyUniquenessByFile:
    """파일별 캐시 키 고유성 테스트."""
    
    @given(
        file_set_a=st.lists(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'N'))),
            min_size=1,
            max_size=3,
            unique=True,
        ),
        file_set_b=st.lists(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'N'))),
            min_size=1,
            max_size=3,
            unique=True,
        ),
    )
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_different_files_different_keys(
        self, file_set_a: List[str], file_set_b: List[str]
    ):
        """서로 다른 파일 집합에 대해 서로 다른 캐시 키 property 테스트.
        
        Property: 서로 다른 파일 집합은 서로 다른 캐시 키를 생성해야 한다.
        (단, 파일 집합이 동일하면 동일한 키)
        
        **Validates: Requirements 7.2**
        """
        # 두 파일 집합이 동일하면 테스트 스킵
        assume(set(file_set_a) != set(file_set_b))
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cache_dir = tmp_path / "cache"
            cache_dir.mkdir()
            
            manager = CacheManager(cache_dir=cache_dir)
            
            # 파일 집합 A 생성
            files_a = []
            for i, content in enumerate(file_set_a):
                file_path = tmp_path / f"a_file_{i}.txt"
                file_path.write_text(content)
                files_a.append(file_path)
            
            # 파일 집합 B 생성
            files_b = []
            for i, content in enumerate(file_set_b):
                file_path = tmp_path / f"b_file_{i}.txt"
                file_path.write_text(content)
                files_b.append(file_path)
            
            key_a = manager.get_cache_key(files_a)
            key_b = manager.get_cache_key(files_b)
            
            # 서로 다른 파일 집합이므로 다른 키
            assert key_a != key_b, \
                "Different file sets should produce different cache keys"


# =============================================================================
# Global Cache Manager Tests
# =============================================================================


class TestGlobalCacheManager:
    """get_cache_manager() 글로벌 인스턴스 테스트."""
    
    def test_singleton_pattern(self, monkeypatch):
        """싱글톤 패턴 테스트."""
        # 글로벌 인스턴스 초기화
        import src.utils.cache_manager as cm_module
        monkeypatch.setattr(cm_module, "_default_cache_manager", None)
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 첫 번째 호출
            manager1 = get_cache_manager(cache_dir=tmp_dir)
            
            # 두 번째 호출
            manager2 = get_cache_manager()
            
            # 동일 인스턴스
            assert manager1 is manager2


# =============================================================================
# Integration Tests
# =============================================================================


class TestCacheManagerIntegration:
    """CacheManager 통합 테스트."""
    
    def test_full_workflow(self, tmp_path: Path):
        """전체 워크플로우 통합 테스트."""
        cache_dir = tmp_path / "cache"
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        
        manager = CacheManager(cache_dir=cache_dir)
        
        # 1. 입력 파일 생성
        input_files = []
        for i in range(3):
            file_path = data_dir / f"input_{i}.parquet"
            file_path.write_text(f"parquet_content_{i}")
            input_files.append(file_path)
        
        # 2. 첫 번째 계산
        computation_count = [0]
        
        def expensive_computation():
            computation_count[0] += 1
            return {"result": f"computed_v{computation_count[0]}"}
        
        result1 = manager.get_or_compute(
            input_files=input_files,
            compute_fn=expensive_computation,
            description="First computation",
        )
        
        assert result1 == {"result": "computed_v1"}
        assert computation_count[0] == 1
        
        # 3. 캐시 히트 확인
        result2 = manager.get_or_compute(
            input_files=input_files,
            compute_fn=expensive_computation,
        )
        
        assert result2 == {"result": "computed_v1"}  # 캐시된 결과
        assert computation_count[0] == 1  # 계산 안 함
        
        # 4. 파일 변경 후 캐시 무효화 확인
        time.sleep(0.01)
        input_files[1].write_text("modified_parquet_content")
        
        result3 = manager.get_or_compute(
            input_files=input_files,
            compute_fn=expensive_computation,
        )
        
        assert result3 == {"result": "computed_v2"}  # 새로 계산
        assert computation_count[0] == 2
        
        # 5. 캐시 정보 확인
        info = manager.get_cache_info()
        assert info["total_files"] >= 2  # 최소 2개 캐시 파일
        
        # 6. 캐시 정리
        deleted = manager.clear()
        assert deleted >= 4  # pkl + json 파일
        
        # 7. 캐시 비어 있는지 확인
        info_after_clear = manager.get_cache_info()
        assert info_after_clear["total_files"] == 0
