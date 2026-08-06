# Python Performance Tips

## List Comprehensions and Generator Expressions

List comprehensions are faster than equivalent for-loops because they are optimised
at the bytecode level and avoid repeated attribute lookups on the list.append method.

```python
# Slower
squares = []
for x in range(1000):
    squares.append(x * x)

# Faster
squares = [x * x for x in range(1000)]
```

Use a **generator expression** when you only need to iterate once — it avoids
allocating the entire list in memory:

```python
total = sum(x * x for x in range(1_000_000))  # O(1) memory
```

## Generators and Lazy Evaluation

Generators use `yield` to produce values on demand, keeping memory use constant
regardless of the dataset size.

```python
def chunked(iterable, size):
    buf = []
    for item in iterable:
        buf.append(item)
        if len(buf) == size:
            yield buf
            buf = []
    if buf:
        yield buf
```

`itertools` provides ready-made lazy iterators: `chain`, `islice`, `groupby`, `product`.

## Dataclasses

`@dataclass` auto-generates `__init__`, `__repr__`, and `__eq__` from field annotations.

```python
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float
    tags: list[str] = field(default_factory=list)
```

`frozen=True` makes instances hashable; `slots=True` (3.10+) reduces memory by ~30%
and speeds attribute access by avoiding the instance `__dict__`.

## String Formatting

Prefer f-strings for readability and speed — they are compiled at parse time:

```python
name, value = "threshold", 0.95
msg = f"{name}={value:.3f}"   # fast, readable
```

When building many strings in a loop, `"".join(parts)` is O(n) vs repeated `+=` which is O(n²).

## Profiling

Always profile before optimizing:

```bash
python -m cProfile -s cumulative my_script.py | head -30
```

`line_profiler` (`pip install line-profiler`) gives per-line timing with `@profile`.
`memory_profiler` tracks per-line memory. `py-spy` profiles without modifying code.

## Avoiding Common Slow Patterns

| Slow | Fast | Why |
|------|------|-----|
| `x in list` | `x in set` | O(n) vs O(1) average |
| `dict.get(k)` in loop | Cache the bound method | Avoids repeated `__getattr__` |
| `re.compile` inside loop | Compile once outside | Avoids recompilation overhead |
| `global` variable reads | Assign to local | Local LOAD_FAST < LOAD_GLOBAL |

## Slot Classes for Hot Paths

If you create millions of instances, `__slots__` eliminates the per-instance `__dict__`:

```python
class Vector:
    __slots__ = ("x", "y", "z")
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z
```
