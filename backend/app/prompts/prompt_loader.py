"""从文件系统加载带版本号的 Prompt（`CODEBUDDY.md`「Prompt 版本管理规范」）。

规则：
1. Prompt 全部存放在仓库根 `prompts/`，文件名格式 `{name}_v{N}.md`；
2. 修改 Prompt **必须新增版本文件**，不得原地覆盖历史版本；
3. Python 代码只允许经本模块加载，**禁止硬编码 Prompt 文本**；
4. 占位符语法 `{{var}}`：**缺变量报错、未知变量报错**，禁止静默留空。

用法：
    template = load_prompt("kg_qa")        # 取最大版本 kg_qa_v1.md
    text = template.render(question="...", context="...")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

#: `{name}_v{N}.md`，name 只允许小写字母 / 数字 / 下划线
PROMPT_FILENAME_PATTERN = re.compile(
    r"^(?P<name>[a-z0-9][a-z0-9_]*)_v(?P<version>\d+)\.md$"
)

#: 占位符 `{{var}}`
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class PromptError(Exception):
    """Prompt 相关错误基类。"""


class PromptNotFoundError(PromptError):
    """Prompt 目录缺失，或指定 name / version 不存在。"""


class PromptRenderError(PromptError):
    """占位符缺失或传入未声明的变量。"""


@dataclass(frozen=True, slots=True)
class PromptRef:
    """Prompt 文件引用。"""

    name: str
    version: int
    path: Path


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """已加载的 Prompt 模板。"""

    name: str
    version: int
    path: Path
    raw: str

    @property
    def placeholders(self) -> tuple[str, ...]:
        """模板声明的变量，按首次出现顺序去重。"""
        seen: list[str] = []
        for match in PLACEHOLDER_PATTERN.finditer(self.raw):
            key = match.group("key")
            if key not in seen:
                seen.append(key)
        return tuple(seen)

    def render(self, **values: str) -> str:
        """渲染模板。缺变量 / 未知变量均抛 `PromptRenderError`。"""
        declared = self.placeholders
        missing = [key for key in declared if key not in values]
        if missing:
            raise PromptRenderError(
                f"{self.name}_v{self.version} 缺少变量: {', '.join(missing)}"
            )
        unknown = [key for key in values if key not in declared]
        if unknown:
            raise PromptRenderError(
                f"{self.name}_v{self.version} 收到未声明的变量: {', '.join(unknown)}"
            )
        return PLACEHOLDER_PATTERN.sub(lambda m: str(values[m.group("key")]), self.raw)


def prompts_root() -> Path:
    """当前生效的 Prompt 目录（可经 `PROMPTS_DIR` 覆盖）。"""
    return Path(get_settings().prompts_dir)


@lru_cache(maxsize=1)
def _index() -> dict[str, tuple[PromptRef, ...]]:
    """扫描并索引 Prompt 文件；结果进程内缓存（新增文件需重启或 `clear_cache()`）。"""
    root = prompts_root()
    if not root.is_dir():
        raise PromptNotFoundError(f"Prompt 目录不存在: {root}")

    grouped: dict[str, list[PromptRef]] = {}
    for path in sorted(root.glob("*.md")):
        match = PROMPT_FILENAME_PATTERN.match(path.name)
        if match is None:
            # README 等非版本化文件按约定忽略
            continue
        name = match.group("name")
        grouped.setdefault(name, []).append(
            PromptRef(name=name, version=int(match.group("version")), path=path)
        )
    return {
        name: tuple(sorted(refs, key=lambda r: r.version))
        for name, refs in grouped.items()
    }


def list_prompts() -> tuple[PromptRef, ...]:
    """列出全部已登记 Prompt（按 name 字典序，同 name 按 version 升序）。"""
    index = _index()
    return tuple(ref for name in sorted(index) for ref in index[name])


def resolve_prompt(name: str, version: int | None = None) -> PromptRef:
    """定位 Prompt 文件；`version=None` 取该 name 的**最大版本**。"""
    index = _index()
    refs = index.get(name)
    if not refs:
        raise PromptNotFoundError(
            f"未找到 Prompt: {name}（可用: {', '.join(sorted(index)) or '无'}）"
        )
    if version is None:
        return refs[-1]
    for ref in refs:
        if ref.version == version:
            return ref
    raise PromptNotFoundError(
        f"未找到 Prompt: {name}_v{version}（可用版本: {', '.join(str(r.version) for r in refs)}）"
    )


@lru_cache(maxsize=64)
def _read_text(path_str: str) -> str:
    return Path(path_str).read_text(encoding="utf-8")


def load_prompt(name: str, version: int | None = None) -> PromptTemplate:
    """加载 Prompt 模板。"""
    ref = resolve_prompt(name, version)
    return PromptTemplate(
        name=ref.name,
        version=ref.version,
        path=ref.path,
        raw=_read_text(str(ref.path)),
    )


def clear_cache() -> None:
    """清空缓存（测试与热更新用）。"""
    _index.cache_clear()
    _read_text.cache_clear()
