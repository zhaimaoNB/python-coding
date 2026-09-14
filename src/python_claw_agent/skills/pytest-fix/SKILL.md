---
name: pytest-fix
description: pytest 失败、测试变红、补测试或修断言时使用。
triggers: pytest, 测试失败, 测试红, 断言, 补测试, failed tests, 单测, 测试挂了, 测试报错, 修测试, AssertionError, pytest failed, 测试没过
---

# pytest 修复流程

1. 先用 bash 复现：能定位到文件就跑 `python -m pytest -q 路径`，否则 `python -m pytest -q`。不要还没看到失败就改代码。
2. 读失败输出，用 `read_file` 打开对应测试和被测实现。搜索符号用 `grep`，不要用 bash 的 findstr / Select-String。
3. 做最小修复：优先改实现让测试恢复原意。用户没要求时不要删测试、不要加 `pytest.skip`、不要扩大断言范围。
4. 改完后重跑刚才那条失败测试，确认变绿。若失败转移到别处，继续读报错，不要连开新功能。
5. 需要补测试时，对着现有 `tests/test_*.py` 的风格写，保持不依赖真实 API。
