---
name: Bug report
about: mdgoat did something wrong (false positive, bad fix, crash)
title: ""
labels: bug
assignees: ""
---

**What happened**
A clear description of the incorrect behavior.

**Input**
The markdown that triggered it. Because payloads are often invisible, a hex or
`\u` dump is ideal:

```python
# e.g. repr() of the offending string
```

**Command / call**
```bash
mdgoat scan ...
```

**Expected**
What you expected instead.

**Environment**
- mdgoat version (`mdgoat --version`):
- Python version:
- OS:
