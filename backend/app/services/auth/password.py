"""口令哈希与校验（P6-P1 留下的「算法终选」在此收口）。

**为什么是 PBKDF2-SHA256 / stdlib，而不是 bcrypt / argon2**：

`scripts/seed_dev_rbac.py`（P6-P1）插第一行 `users` 时已经用了这个算法与这个串格式
（`pbkdf2_sha256$<迭代数>$<salt_b64>$<hash_b64>`），并在注释里写明「算法的最终选型归
**P2-C** —— 届时才有校验方」。本批就是那个"届时"，选型的三条判据：

1. **零新增依赖** —— ``hashlib.pbkdf2_hmac`` + ``hmac.compare_digest`` 都在标准库里；
   为一条 ``NOT NULL`` 列引入 ``passlib`` / ``argon2-cffi`` 属「无消费者依赖」
   （预留纪律第 6 条，历史病例 ``task_retry_multiplier``）。
2. **零迁移** —— 沿用既有串格式 ⇒ 演示库里那一行已有的哈希**不需要**重算或回填。
3. **参数不含糊** —— 迭代数随串落地（不是常量），将来上调迭代数不必一次性重算全表：
   老串按串里的旧值验，新哈希按新值写，逐个自然轮换。

**算法偏离 spec 的登记**：`specs/m5-permission-audit.md` §4.1 写的是「bcrypt / argon2」。
本仓选 PBKDF2-SHA256（OWASP 对 SHA-256 的推荐量级 600k），理由同上第 1 条；
**不做**「先引入 bcrypt 再迁移」——那会在一个还没有第二个校验方的字段上多付一次迁移成本。
若日后客户审计点名要求 argon2id，届时按上面的第 3 条做**增量轮换**，不重写历史。

**不做什么**：口令强度策略 / 找回 / 过期 / 历史去重 —— 均不在 P2-C 边界内（Non-goal 9）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

#: 迭代数（OWASP 对 PBKDF2-HMAC-SHA256 的推荐量级）。**随串落地**，见模块 docstring 第 3 条。
PBKDF2_ITERATIONS = 600_000

#: 盐长度（字节）
_SALT_BYTES = 16

_SCHEME = "pbkdf2_sha256"


def hash_password(raw: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    """把明文口令编码成**可自描述**的哈希串（含迭代数与盐）。

    **绝不**返回明文、绝不打印；调用方负责不把 ``raw`` 落日志。
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt, iterations)
    return (
        f"{_SCHEME}${iterations}$"
        f"{base64.b64encode(salt).decode('ascii')}$"
        f"{base64.b64encode(derived).decode('ascii')}"
    )


def verify_password(raw: str, stored: str) -> bool:
    """校验明文口令是否匹配哈希串；**任何**畸形 / 不匹配一律 ``False``。

    **为什么失败不抛异常**：口令校验的失败只有一种对外语义（"用户名或口令不正确"），
    把「哈希串格式坏了」和「口令不对」分成两种错误，等于给攻击者一条探测列内容的旁路。
    （代价：哈希串损坏表现为"所有人都登录不上"而不是一条显式报错——该排查路径
    写在 `scripts/seed_dev_rbac.py --check` 与 `tests/test_login_flow.py` 里。）

    **恒定时间比对**：``hmac.compare_digest``，避免因早退泄漏"前 n 字节是对的"。
    """
    try:
        scheme, raw_iterations, salt_b64, hash_b64 = stored.split("$")
        iterations = int(raw_iterations)
        if scheme != _SCHEME or iterations <= 0:
            return False
        expected = base64.b64decode(hash_b64.encode("ascii"), validate=True)
        salt = base64.b64decode(salt_b64.encode("ascii"), validate=True)
    except (ValueError, TypeError):
        return False

    derived = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt, iterations)
    # 长度不同也走 compare_digest（它先比长度再比内容，仍保持恒定时间语义）
    return hmac.compare_digest(derived, expected)


__all__ = ["PBKDF2_ITERATIONS", "hash_password", "verify_password"]
