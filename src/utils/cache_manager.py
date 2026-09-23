"""
Cache Manager Module

전처리 결과 캐싱을 관리하는 모듈.
입력 파일의 수정 시각(mtime)을 기반으로 캐시 키를 생성하고,
캐시 유효성을 검증하며, 결과를 저장/로드한다.

Requirements:
    - 7.2: 입력 파일의 수정 시각이 변경되지 않은 경우, 재실행 시 전처리 단계를 건너뛰고 캐시를 재사용
"""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class CacheInfo:
    """캐시 상태 정보.
    
    Attributes:
        total_files: 캐시 파일 총 개수
        total_size_bytes: 총 캐시 크기 (바이트)
        oldest_file: 가장 오래된 캐시 파일 이름
        oldest_mtime: 가장 오래된 캐시 파일 수정 시각
        newest_file: 가장 최신 캐시 파일 이름
        newest_mtime: 가장 최신 캐시 파일 수정 시각
    """
    total_files: int
    total_size_bytes: int
    oldest_file: Optional[str] = None
    oldest_mtime: Optional[datetime] = None
    newest_file: Optional[str] = None
    newest_mtime: Optional[datetime] = None


@dataclass
class CacheMetadata:
    """캐시 메타데이터.
    
    Attributes:
        cache_key: 캐시 키
        created_at: 캐시 생성 시각
        input_files: 입력 파일 정보 리스트 (경로, mtime)
        description: 캐시 설명 (선택)
    """
    cache_key: str
    created_at: str
    input_files: List[Dict[str, Any]] = field(default_factory=list)
    description: Optional[str] = None


class CacheManager:
    """전처리 결과 캐시 관리자.
    
    입력 파일의 수정 시각(mtime)을 기반으로 캐시 키를 생성하고,
    캐시 유효성을 검증하며, 결과를 저장/로드한다.
    
    Attributes:
        cache_dir: 캐시 파일 저장 디렉토리 (기본: data/cache/)
        
    Requirements:
        - 7.2: 입력 파일의 수정 시각이 변경되지 않은 경우, 
               재실행 시 전처리 단계를 건너뛰고 캐시를 재사용
    """
    
    CACHE_FILE_EXTENSION = ".pkl"
    METADATA_FILE_EXTENSION = ".json"
    
    def __init__(self, cache_dir: Union[str, Path] = "data/cache") -> None:
        """CacheManager 초기화.
        
        Args:
            cache_dir: 캐시 파일 저장 디렉토리
        """
        self.cache_dir = Path(cache_dir)
        self._ensure_cache_dir()
        
        logger.debug(
            "CacheManager initialized",
            extra={"cache_dir": str(self.cache_dir)}
        )
    
    def _ensure_cache_dir(self) -> None:
        """캐시 디렉토리가 존재하지 않으면 생성."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_file_path(self, cache_key: str) -> Path:
        """캐시 파일 경로 반환.
        
        Args:
            cache_key: 캐시 키
            
        Returns:
            캐시 파일 경로 (.pkl)
        """
        return self.cache_dir / f"{cache_key}{self.CACHE_FILE_EXTENSION}"
    
    def _get_metadata_file_path(self, cache_key: str) -> Path:
        """메타데이터 파일 경로 반환.
        
        Args:
            cache_key: 캐시 키
            
        Returns:
            메타데이터 파일 경로 (.json)
        """
        return self.cache_dir / f"{cache_key}{self.METADATA_FILE_EXTENSION}"
    
    def get_cache_key(self, input_files: List[Union[str, Path]]) -> str:
        """입력 파일 수정 시각 기반 캐시 키 생성.
        
        각 파일의 (경로, mtime) 정보를 결합하여 SHA-256 해시 생성.
        파일은 경로 기준으로 정렬하여 순서에 무관하게 동일한 키를 생성한다.
        
        Args:
            input_files: 입력 파일 경로 리스트
            
        Returns:
            SHA-256 해시 문자열 (64자)
            
        Raises:
            FileNotFoundError: 입력 파일이 존재하지 않는 경우
        """
        if not input_files:
            # 빈 리스트의 경우도 고유한 해시 반환
            return hashlib.sha256(b"empty_input").hexdigest()
        
        # 파일 정보 수집 및 정렬
        file_info_list: List[tuple[str, float]] = []
        
        for file_path in input_files:
            path = Path(file_path)
            
            if not path.exists():
                raise FileNotFoundError(f"Input file not found: {path}")
            
            # 절대 경로와 mtime을 사용
            abs_path = str(path.resolve())
            mtime = path.stat().st_mtime
            file_info_list.append((abs_path, mtime))
        
        # 경로 기준 정렬 (순서 일관성 보장)
        file_info_list.sort(key=lambda x: x[0])
        
        # 해시 생성
        hash_input = json.dumps(file_info_list, sort_keys=True).encode("utf-8")
        cache_key = hashlib.sha256(hash_input).hexdigest()
        
        logger.debug(
            "Cache key generated",
            extra={
                "cache_key": cache_key[:16] + "...",
                "num_files": len(file_info_list),
            }
        )
        
        return cache_key
    
    def is_valid(self, cache_key: str) -> bool:
        """캐시 유효성 검증.
        
        해당 캐시 키에 대한 캐시 파일(.pkl)이 존재하는지 확인.
        메타데이터 파일(.json)은 선택적이므로 검사하지 않는다.
        
        Args:
            cache_key: 캐시 키
            
        Returns:
            캐시가 유효하면 True, 아니면 False
        """
        cache_file = self._get_cache_file_path(cache_key)
        is_cache_valid = cache_file.exists()
        
        logger.debug(
            "Cache validity checked",
            extra={
                "cache_key": cache_key[:16] + "...",
                "is_valid": is_cache_valid,
            }
        )
        
        return is_cache_valid
    
    def load(self, cache_key: str) -> Optional[Any]:
        """캐시된 결과 로드.
        
        Args:
            cache_key: 캐시 키
            
        Returns:
            캐시된 객체 또는 None (캐시 없음 또는 로드 실패 시)
        """
        cache_file = self._get_cache_file_path(cache_key)
        
        if not cache_file.exists():
            logger.debug(
                "Cache file not found",
                extra={"cache_key": cache_key[:16] + "..."}
            )
            return None
        
        try:
            with open(cache_file, "rb") as f:
                data = pickle.load(f)
            
            logger.info(
                "Cache loaded successfully",
                extra={
                    "cache_key": cache_key[:16] + "...",
                    "cache_file": str(cache_file),
                }
            )
            
            return data
            
        except (pickle.UnpicklingError, EOFError, ModuleNotFoundError) as e:
            logger.warning(
                "Failed to load cache",
                extra={
                    "cache_key": cache_key[:16] + "...",
                    "error": str(e),
                }
            )
            return None
    
    def save(
        self, 
        cache_key: str, 
        data: Any,
        input_files: Optional[List[Union[str, Path]]] = None,
        description: Optional[str] = None
    ) -> Path:
        """결과를 캐시에 저장.
        
        데이터를 pickle 형식으로 저장하고, 
        메타데이터(생성 시각, 입력 파일 정보 등)를 JSON으로 저장한다.
        
        Args:
            cache_key: 캐시 키
            data: 저장할 데이터 (pickle 직렬화 가능해야 함)
            input_files: 입력 파일 경로 리스트 (메타데이터용, 선택)
            description: 캐시 설명 (메타데이터용, 선택)
            
        Returns:
            저장된 캐시 파일 경로
            
        Raises:
            pickle.PicklingError: 데이터를 pickle로 직렬화할 수 없는 경우
        """
        self._ensure_cache_dir()
        
        cache_file = self._get_cache_file_path(cache_key)
        metadata_file = self._get_metadata_file_path(cache_key)
        
        # 데이터 저장 (pickle)
        with open(cache_file, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        # 메타데이터 생성 및 저장
        input_file_info = []
        if input_files:
            for file_path in input_files:
                path = Path(file_path)
                if path.exists():
                    input_file_info.append({
                        "path": str(path.resolve()),
                        "mtime": path.stat().st_mtime,
                        "size_bytes": path.stat().st_size,
                    })
        
        metadata = CacheMetadata(
            cache_key=cache_key,
            created_at=datetime.now().isoformat(),
            input_files=input_file_info,
            description=description,
        )
        
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "cache_key": metadata.cache_key,
                    "created_at": metadata.created_at,
                    "input_files": metadata.input_files,
                    "description": metadata.description,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        
        logger.info(
            "Cache saved successfully",
            extra={
                "cache_key": cache_key[:16] + "...",
                "cache_file": str(cache_file),
                "cache_size_bytes": cache_file.stat().st_size,
            }
        )
        
        return cache_file
    
    def clear(self, pattern: Optional[str] = None) -> int:
        """캐시 정리.
        
        Args:
            pattern: 삭제할 캐시 파일 패턴 (None이면 전체 삭제)
                     예: "preprocessor_*" - preprocessor로 시작하는 캐시만 삭제
            
        Returns:
            삭제된 파일 수
        """
        deleted_count = 0
        
        if pattern:
            # 패턴에 맞는 파일만 삭제
            pkl_files = list(self.cache_dir.glob(f"{pattern}{self.CACHE_FILE_EXTENSION}"))
            json_files = list(self.cache_dir.glob(f"{pattern}{self.METADATA_FILE_EXTENSION}"))
            files_to_delete = pkl_files + json_files
        else:
            # 모든 캐시 파일 삭제
            pkl_files = list(self.cache_dir.glob(f"*{self.CACHE_FILE_EXTENSION}"))
            json_files = list(self.cache_dir.glob(f"*{self.METADATA_FILE_EXTENSION}"))
            files_to_delete = pkl_files + json_files
        
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                deleted_count += 1
            except OSError as e:
                logger.warning(
                    "Failed to delete cache file",
                    extra={"file": str(file_path), "error": str(e)}
                )
        
        logger.info(
            "Cache cleared",
            extra={
                "pattern": pattern or "*",
                "deleted_count": deleted_count,
            }
        )
        
        return deleted_count
    
    def get_cache_info(self) -> Dict[str, Any]:
        """캐시 상태 정보 반환.
        
        Returns:
            캐시 파일 수, 총 크기, 가장 오래된/최신 파일 등의 정보 딕셔너리
        """
        pkl_files = list(self.cache_dir.glob(f"*{self.CACHE_FILE_EXTENSION}"))
        
        if not pkl_files:
            return {
                "total_files": 0,
                "total_size_bytes": 0,
                "total_size_mb": 0.0,
                "oldest_file": None,
                "oldest_mtime": None,
                "newest_file": None,
                "newest_mtime": None,
                "cache_dir": str(self.cache_dir),
            }
        
        total_size = sum(f.stat().st_size for f in pkl_files)
        
        # mtime 기준 정렬
        files_with_mtime = [
            (f, datetime.fromtimestamp(f.stat().st_mtime)) 
            for f in pkl_files
        ]
        files_with_mtime.sort(key=lambda x: x[1])
        
        oldest_file, oldest_mtime = files_with_mtime[0]
        newest_file, newest_mtime = files_with_mtime[-1]
        
        return {
            "total_files": len(pkl_files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "oldest_file": oldest_file.name,
            "oldest_mtime": oldest_mtime.isoformat(),
            "newest_file": newest_file.name,
            "newest_mtime": newest_mtime.isoformat(),
            "cache_dir": str(self.cache_dir),
        }
    
    def get_or_compute(
        self,
        input_files: List[Union[str, Path]],
        compute_fn: callable,
        description: Optional[str] = None,
    ) -> Any:
        """캐시된 결과를 반환하거나, 없으면 계산하여 저장 후 반환.
        
        이 메서드는 캐시 사용의 일반적인 패턴을 단순화한다:
        1. 입력 파일 기반으로 캐시 키 생성
        2. 캐시가 유효하면 로드하여 반환
        3. 캐시가 없으면 compute_fn을 실행하고 결과를 저장
        
        Args:
            input_files: 입력 파일 경로 리스트
            compute_fn: 캐시가 없을 때 실행할 함수 (인자 없음)
            description: 캐시 설명 (메타데이터용, 선택)
            
        Returns:
            캐시된 결과 또는 새로 계산된 결과
        """
        cache_key = self.get_cache_key(input_files)
        
        if self.is_valid(cache_key):
            cached_data = self.load(cache_key)
            if cached_data is not None:
                logger.info(
                    "Using cached result",
                    extra={
                        "cache_key": cache_key[:16] + "...",
                        "num_input_files": len(input_files),
                    }
                )
                return cached_data
        
        # 캐시 없음 또는 로드 실패 - 계산 수행
        logger.info(
            "Computing result (cache miss)",
            extra={
                "cache_key": cache_key[:16] + "...",
                "num_input_files": len(input_files),
            }
        )
        
        result = compute_fn()
        
        self.save(cache_key, result, input_files=input_files, description=description)
        
        return result


# 편의를 위한 기본 캐시 매니저 인스턴스 (lazy initialization)
_default_cache_manager: Optional[CacheManager] = None


def get_cache_manager(cache_dir: Union[str, Path] = "data/cache") -> CacheManager:
    """기본 CacheManager 인스턴스를 반환.
    
    첫 호출 시 인스턴스를 생성하고, 이후 호출에서는 동일 인스턴스를 반환한다.
    다른 cache_dir가 필요한 경우 CacheManager를 직접 생성하여 사용한다.
    
    Args:
        cache_dir: 캐시 디렉토리 경로 (첫 호출 시에만 적용)
        
    Returns:
        CacheManager 인스턴스
    """
    global _default_cache_manager
    
    if _default_cache_manager is None:
        _default_cache_manager = CacheManager(cache_dir)
    
    return _default_cache_manager
