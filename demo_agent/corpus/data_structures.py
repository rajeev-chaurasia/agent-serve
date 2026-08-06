# data_structures.py — Linked list and stack implementations
# Both structures are generic (work with any comparable element type).


# --- Singly Linked List ---

class Node:
    """A single node in the linked list."""
    __slots__ = ("value", "next")

    def __init__(self, value):
        self.value = value
        self.next = None


class LinkedList:
    """Singly linked list with O(1) prepend, O(n) append and search."""

    def __init__(self):
        self._head: Node | None = None
        self._size: int = 0

    def prepend(self, value) -> None:
        """Insert value at the front of the list. O(1)."""
        node = Node(value)
        node.next = self._head
        self._head = node
        self._size += 1

    def append(self, value) -> None:
        """Insert value at the tail of the list. O(n)."""
        node = Node(value)
        if self._head is None:
            self._head = node
        else:
            cur = self._head
            while cur.next:
                cur = cur.next
            cur.next = node
        self._size += 1

    def delete(self, value) -> bool:
        """Remove first occurrence of value. Returns True if found. O(n)."""
        prev, cur = None, self._head
        while cur:
            if cur.value == value:
                if prev:
                    prev.next = cur.next
                else:
                    self._head = cur.next
                self._size -= 1
                return True
            prev, cur = cur, cur.next
        return False

    def search(self, value) -> Node | None:
        """Return the first node with the given value, or None. O(n)."""
        cur = self._head
        while cur:
            if cur.value == value:
                return cur
            cur = cur.next
        return None

    def to_list(self) -> list:
        result, cur = [], self._head
        while cur:
            result.append(cur.value)
            cur = cur.next
        return result

    def __len__(self) -> int:
        return self._size

    def __repr__(self) -> str:
        return " -> ".join(str(v) for v in self.to_list())


# --- Stack ---

class Stack:
    """
    LIFO stack backed by a Python list.
    push / pop / peek are all O(1) amortized.
    """

    def __init__(self):
        self._data: list = []

    def push(self, value) -> None:
        """Push value onto the top of the stack."""
        self._data.append(value)

    def pop(self):
        """Remove and return the top element. Raises IndexError if empty."""
        if not self._data:
            raise IndexError("pop from empty stack")
        return self._data.pop()

    def peek(self):
        """Return the top element without removing it. Raises IndexError if empty."""
        if not self._data:
            raise IndexError("peek at empty stack")
        return self._data[-1]

    def is_empty(self) -> bool:
        return len(self._data) == 0

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"Stack({self._data!r})"
