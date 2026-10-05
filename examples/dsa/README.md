# X DSA patterns

These are 20 standalone, runnable X programs. Each file includes a small
`main()` demonstration; run one with:

```sh
x run examples/dsa/05_longest_unique_substring.x
x run examples/dsa/07_container_most_water.x
x run examples/dsa/20_run_length_codec.x
```

They use only X language features and built-ins; no imports or packages are
needed. The examples are teaching implementations, with the usual constraints
noted below. `integer function name(...)` and `string function name(...)`
show X's return-type-before-`function` syntax.

| # | Problem | Pattern | Time | Extra space |
|---|---|---|---:|---:|
| 01 | Two Sum | Hash map | O(n) | O(n) |
| 02 | Maximum Subarray | Kadane's algorithm | O(n) | O(1) |
| 03 | Move Zeroes | In-place two pointers | O(n) | O(1) |
| 04 | Best Time to Buy and Sell Stock | Running minimum | O(n) | O(1) |
| 05 | Longest Substring Without Repeating Characters | Sliding window + last-seen map | O(n) | O(k) |
| 06 | Minimum Size Subarray Sum | Variable sliding window | O(n) | O(1) |
| 07 | Container With Most Water | Two pointers | O(n) | O(1) |
| 08 | Remove Duplicates from Sorted Array | Read/write pointers | O(n) | O(1) |
| 09 | Valid Palindrome | Two pointers | O(n) | O(1) |
| 10 | Binary Search | Binary lifting / ordered search | O(log n) | O(log n) |
| 11 | Lower Bound / First Insert Position | Binary lifting boundary search | O(log n) | O(log n) |
| 12 | Valid Parentheses | Stack | O(n) | O(n) |
| 13 | Next Greater Element | Monotonic stack | O(n) | O(n) |
| 14 | Merge Two Sorted Arrays | Two pointers | O(n + m) | O(n + m) |
| 15 | Range Sum Query | Prefix sums | O(n) build, O(1) query | O(n) |
| 16 | Factorial | Recursion / base cases | O(n) | O(n) call stack |
| 17 | Fibonacci | Memoized recursion | O(n) | O(n) |
| 18 | Matrix Diagonal Sum | Matrix traversal | O(n) | O(1) |
| 19 | Flood Fill | Depth-first search | O(rows × columns) | O(rows × columns) call stack |
| 20 | Run-Length Encode / Decode | String scan | O(n) | O(n) |

## Notes

- The longest-substring example handles arbitrary characters available through
  X's string indexing; its map stores each character's latest index.
- The minimum-size-subarray example assumes all input values are positive, as
  in the standard problem.
- The palindrome example compares characters exactly; it intentionally does
  not normalize punctuation or letter case.
- Flood fill uses recursive DFS. Very large regions may exceed the interpreter's
  recursion depth.
- X currently uses floating-point division for `/`; the two binary-search
  examples avoid fractional array indexes by descending powers of two. This
  keeps logarithmic time at the cost of storing those powers.
- The run-length format puts a repeat count after a character, so `aaab`
  becomes `a3b`. The teaching codec assumes input text uses letters; digits are
  reserved for counts, making the encoding unambiguous for that alphabet.
