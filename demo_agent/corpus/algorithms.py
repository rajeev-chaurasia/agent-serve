# algorithms.py — Common search and sort algorithms
# Each function is self-contained with O-notation documented inline.


# --- Binary Search ---
# Precondition: arr must be sorted in ascending order.
# Time: O(log n), Space: O(1) iterative / O(log n) recursive stack.
def binary_search(arr: list, target) -> int:
    """Return the index of target in arr, or -1 if not found."""
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


# --- Quicksort ---
# Average: O(n log n), Worst: O(n^2) on already-sorted input without pivot shuffling.
# Space: O(log n) average stack depth.
def quicksort(arr: list) -> list:
    """Return a new sorted list using the quicksort algorithm."""
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)


def quicksort_inplace(arr: list, lo: int = 0, hi: int = None) -> None:
    """Sort arr in-place using Lomuto partition scheme."""
    if hi is None:
        hi = len(arr) - 1
    if lo < hi:
        p = _partition(arr, lo, hi)
        quicksort_inplace(arr, lo, p - 1)
        quicksort_inplace(arr, p + 1, hi)


def _partition(arr: list, lo: int, hi: int) -> int:
    pivot = arr[hi]
    i = lo - 1
    for j in range(lo, hi):
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]
    arr[i + 1], arr[hi] = arr[hi], arr[i + 1]
    return i + 1


# --- Merge Sort ---
# Time: O(n log n) guaranteed. Space: O(n) auxiliary.
# Stable sort — equal elements retain their original relative order.
def merge_sort(arr: list) -> list:
    """Return a new sorted list using merge sort (stable, O(n log n))."""
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return _merge(left, right)


def _merge(left: list, right: list) -> list:
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result
