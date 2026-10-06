import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from xlang.module_loader import ModuleLoader
from xlang.runtime import Interpreter, RuntimeErrorX


def run_x(source, arguments=None, environment=None):
    """Run an X source string and return ``(result, printed_output)``."""
    with TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        source_file = project_root / "main.x"
        source_file.write_text(source, encoding="utf-8")
        program = ModuleLoader(project_root).load_program(source_file)
        output = []
        result = Interpreter(
            arguments, output.append, environment=environment
        ).interpret(program)
    return result, output


class ArrayMethodTests(unittest.TestCase):
    def test_map_with_arrow_callback(self):
        result, output = run_x("""
            function main() {
                print([1, 2, 3].map((int n) => n * 2));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["[2, 4, 6]"])

    def test_map_callback_receives_index_when_declared(self):
        _, output = run_x("""
            function main() {
                print([10, 20, 30].map((int v, int i) => v + i));
            }
            """)
        self.assertEqual(output, ["[10, 21, 32]"])

    def test_filter_with_arrow_callback(self):
        _, output = run_x("""
            function main() {
                print([1, 2, 3, 4].filter((int n) => n % 2 == 0));
                print([1, 2, 3].filter((int n, int i) => i > 0));
            }
            """)
        self.assertEqual(output, ["[2, 4]", "[2, 3]"])

    def test_reduce_with_and_without_initial_value(self):
        _, output = run_x("""
            function main() {
                print([1, 2, 3].reduce((int a, int b) => a + b));
                print([1, 2, 3].reduce((int a, int b) => a + b, 10));
            }
            """)
        self.assertEqual(output, ["6", "16"])

    def test_reduce_callback_receives_index(self):
        _, output = run_x("""
            function main() {
                print([1, 2, 3].reduce((int a, int b, int i) => a + b + i, 0));
            }
            """)
        self.assertEqual(output, ["9"])

    def test_for_each_visits_elements_and_returns_null(self):
        _, output = run_x("""
            function main() {
                let total = 0;
                [1, 2, 3].forEach((int n) => { total = total + n; });
                print(total);
                print([1, 2].forEach((int n) => n));
            }
            """)
        self.assertEqual(output, ["6", "null"])

    def test_find_some_every(self):
        _, output = run_x("""
            function main() {
                print([1, 2, 3].find((int n) => n > 1));
                print([1, 2, 3].find((int n) => n > 9));
                print([1, 2, 3].some((int n) => n > 2));
                print([1, 2, 3].some((int n) => n > 9));
                print([1, 2, 3].every((int n, int i) => n > i));
                print([1, 2, 3].every((int n) => n > 1));
            }
            """)
        self.assertEqual(output, ["2", "null", "true", "false", "true", "false"])

    def test_index_of_and_contains(self):
        _, output = run_x("""
            function main() {
                print([1, 2, 3].indexOf(2));
                print([1, 2, 3].indexOf(9));
                print(["a", "b"].contains("b"));
                print(["a", "b"].contains("z"));
                print([1, 2].contains(1));
            }
            """)
        self.assertEqual(output, ["1", "-1", "true", "false", "true"])

    def test_sort_default_is_natural_and_stable(self):
        _, output = run_x("""
            function main() {
                print([3, 1, 2].sort());
                print(["pear", "apple"].sort());
                print([1, "x", 3].sort());
                let same = ["b", "a", "c"];
                same.sort((string l, string r) => 0);
                print(same);
            }
            """)
        self.assertEqual(
            output,
            ["[1, 2, 3]", "[apple, pear]", "[1, 3, x]", "[b, a, c]"],
        )

    def test_sort_with_comparator(self):
        _, output = run_x("""
            function main() {
                print([3, 1, 2].sort((int a, int b) => b - a));
                print(["bb", "a", "ccc"].sort((string a, string b) => a.length - b.length));
            }
            """)
        self.assertEqual(output, ["[3, 2, 1]", "[a, bb, ccc]"])

    def test_reverse_returns_the_reversed_array(self):
        _, output = run_x("""
            function main() {
                let values = [1, 2, 3];
                print(values.reverse());
                print(values);
            }
            """)
        self.assertEqual(output, ["[3, 2, 1]", "[3, 2, 1]"])

    def test_slice_supports_optional_and_negative_bounds(self):
        _, output = run_x("""
            function main() {
                print([1, 2, 3, 4].slice());
                print([1, 2, 3, 4].slice(1));
                print([1, 2, 3, 4].slice(1, 3));
                print([1, 2, 3, 4].slice(-2));
                print([1, 2, 3, 4].slice(1, -1));
            }
            """)
        self.assertEqual(
            output,
            ["[1, 2, 3, 4]", "[2, 3, 4]", "[2, 3]", "[3, 4]", "[2, 3]"],
        )

    def test_concat_and_join(self):
        _, output = run_x("""
            function main() {
                print([1, 2].concat([3, 4]));
                print([1, 2, 3].join());
                print([1, 2, 3].join("-"));
                print([1, null, 2].join("|"));
                print([].concat([1]));
            }
            """)
        self.assertEqual(
            output,
            ["[1, 2, 3, 4]", "1,2,3", "1-2-3", "1||2", "[1]"],
        )

    def test_first_last_is_empty_and_clear(self):
        _, output = run_x("""
            function main() {
                let values = [1, 2, 3];
                print(values.first());
                print(values.last());
                print(values.isEmpty());
                values.clear();
                print(values);
                print(values.isEmpty());
                print([].first());
                print([].last());
                print([].isEmpty());
            }
            """)
        self.assertEqual(
            output, ["1", "3", "false", "[]", "true", "null", "null", "true"]
        )

    def test_empty_array_functional_edges(self):
        _, output = run_x("""
            function main() {
                print([].map((int n) => n * 2));
                print([].filter((int n) => n > 0));
                print([].every((int n) => n > 0));
                print([].some((int n) => n > 0));
                print([].find((int n) => n > 0));
                print([].indexOf(1));
                print([].contains(1));
            }
            """)
        self.assertEqual(
            output, ["[]", "[]", "true", "false", "null", "-1", "false"]
        )

    def test_functional_list_form(self):
        _, output = run_x("""
            function main() {
                print(List.map([1, 2, 3], (int n) => n * 2));
                print(List.filter([1, 2, 3], (int n) => n > 1));
                print(List.reduce([1, 2, 3], (int a, int b) => a + b, 0));
                print(List.join(["a", "b"], "-"));
            }
            """)
        self.assertEqual(output, ["[2, 4, 6]", "[2, 3]", "6", "a-b"])

    def test_length_add_and_to_string_still_work(self):
        _, output = run_x("""
            function main() {
                let values = [];
                values.add(7);
                print(values.length);
                print(values);
                print("abc".length);
                print("abc".toString());
            }
            """)
        self.assertEqual(output, ["1", "[7]", "3", "abc"])

    def test_readme_entry_upper_case_via_hashmap_helpers(self):
        _, output = run_x("""
            function main() {
                let map = HashMap.create();
                HashMap.set(map, "alpha", "one");
                HashMap.set(map, "beta", "two");
                function isLong(string[] entry) {
                    return entry[0].length > 3;
                }
                function uppercase(string[] entry) {
                    return [entry[0].toUpperCase(), entry[1]];
                }
                let filtered = HashMap.filter(map, isLong);
                print(filtered);
                let mapped = HashMap.map(map, uppercase);
                print(mapped);
            }
            """)
        self.assertEqual(
            output,
            ["{alpha: one, beta: two}", "{ALPHA: one, BETA: two}"],
        )

    def test_string_index_supports_upper_case(self):
        _, output = run_x("""
            function main() {
                let entry = ["readme", "value"];
                print(entry[0].toUpperCase());
            }
            """)
        self.assertEqual(output, ["README"])

    def test_map_rejects_missing_or_invalid_callback(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.map expects a callback function"
        ):
            run_x("""
                function main() {
                    [1].map();
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.map callback must be a function"
        ):
            run_x("""
                function main() {
                    [1].map(5);
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.filter expects a callback function"
        ):
            run_x("""
                function main() {
                    [1].filter();
                }
                """)

    def test_reduce_rejects_bad_arity_and_empty_without_initial(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.reduce expects a callback function"
        ):
            run_x("""
                function main() {
                    [1].reduce();
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX,
            "Array.reduce of an empty array requires an initial value",
        ):
            run_x("""
                function main() {
                    [].reduce((int a, int b) => a);
                }
                """)

    def test_index_of_contains_and_join_reject_bad_arguments(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.indexOf expects a value argument"
        ):
            run_x("""
                function main() {
                    [1].indexOf();
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.concat expects an array argument"
        ):
            run_x("""
                function main() {
                    [1].concat(5);
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.join separator must be a string"
        ):
            run_x("""
                function main() {
                    [1].join(5);
                }
                """)

    def test_slice_and_sort_reject_bad_bounds_and_results(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.slice indices must be integers"
        ):
            run_x("""
                function main() {
                    [1, 2].slice("x");
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.sort callback must return a number"
        ):
            run_x("""
                function main() {
                    [1, 2].sort((int a, int b) => "nope");
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.sort accepts at most one callback"
        ):
            run_x("""
                function main() {
                    [1, 2].sort((int a) => a, (int b) => b);
                }
                """)

    def test_no_argument_array_methods_reject_arguments(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.first expects no arguments"
        ):
            run_x("""
                function main() {
                    [1].first(2);
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "Array.clear expects no arguments"
        ):
            run_x("""
                function main() {
                    [1].clear(2);
                }
                """)


class StringMethodTests(unittest.TestCase):
    def test_to_upper_case_prints_upper_case(self):
        result, output = run_x("""
            function main() {
                print("abc".toUpperCase());
                print("héllo".toUpperCase());
                print("".toUpperCase());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["ABC", "HÉLLO", ""])

    def test_to_lower_case_and_trim(self):
        _, output = run_x("""
            function main() {
                print("MiXeD".toLowerCase());
                print("  padded  ".trim());
                print("".trim());
            }
            """)
        self.assertEqual(output, ["mixed", "padded", ""])

    def test_starts_with_ends_with_contains(self):
        _, output = run_x("""
            function main() {
                print("hello".startsWith("he"));
                print("hello".startsWith("lo"));
                print("hello".endsWith("lo"));
                print("hello".endsWith("he"));
                print("hello".contains("ell"));
                print("hello".contains("xyz"));
            }
            """)
        self.assertEqual(
            output, ["true", "false", "true", "false", "true", "false"]
        )

    def test_index_of(self):
        _, output = run_x("""
            function main() {
                print("hello".indexOf("l"));
                print("hello".indexOf("z"));
                print("héllo".indexOf("l"));
            }
            """)
        self.assertEqual(output, ["2", "-1", "2"])

    def test_replace_replaces_first_occurrence_only(self):
        _, output = run_x("""
            function main() {
                print("aaa".replace("a", "b"));
                print("a-b-c".replace("-", "+"));
            }
            """)
        self.assertEqual(output, ["baa", "a+b-c"])

    def test_replace_all_replaces_every_occurrence(self):
        _, output = run_x("""
            function main() {
                print("aaa".replaceAll("a", "b"));
                print("a-b-c".replaceAll("-", "+"));
                print("abc".replaceAll("z", "!"));
            }
            """)
        self.assertEqual(output, ["bbb", "a+b+c", "abc"])

    def test_split_variants(self):
        _, output = run_x("""
            function main() {
                print("a,b,c".split(","));
                print("hello world".split());
                print("abc".split(""));
                print("".split(","));
            }
            """)
        self.assertEqual(
            output,
            ["[a, b, c]", "[hello, world]", "[a, b, c]", "[]"],
        )

    def test_char_at_counts_unicode_code_points(self):
        _, output = run_x("""
            function main() {
                print("abc".charAt(0));
                print("abc".charAt(-1));
                print("héllo".charAt(1));
                print("héllo".length);
            }
            """)
        self.assertEqual(output, ["a", "c", "é", "5"])

    def test_substring_uses_javascript_bounds(self):
        _, output = run_x("""
            function main() {
                print("hello".substring(1, 3));
                print("hello".substring(3, 1));
                print("hello".substring(2));
                print("hello".substring(-5, 2));
            }
            """)
        self.assertEqual(output, ["el", "el", "llo", "he"])

    def test_slice_counts_negatives_from_the_end(self):
        _, output = run_x("""
            function main() {
                print("hello".slice(1, 3));
                print("hello".slice(-2));
                print("hello".slice(1, -1));
                print("hello".slice());
            }
            """)
        self.assertEqual(output, ["el", "lo", "ell", "hello"])

    def test_repeat(self):
        _, output = run_x("""
            function main() {
                print("ab".repeat(3));
                print("ab".repeat(0));
                print("".repeat(5));
            }
            """)
        self.assertEqual(output, ["ababab", "", ""])

    def test_pad_start_and_pad_end(self):
        _, output = run_x("""
            function main() {
                print("hi".padStart(5));
                print("hi".padStart(5, "*"));
                print("hi".padStart(5, "ab"));
                print("hi".padEnd(5));
                print("hi".padEnd(5, "*"));
                print("hi".padEnd(5, "ab"));
                print("hi".padStart(1));
                print("hi".padStart(5, ""));
            }
            """)
        self.assertEqual(
            output,
            ["   hi", "***hi", "abahi", "hi   ", "hi***", "hiaba", "hi", "hi"],
        )

    def test_is_empty_to_char_array_length_and_to_string(self):
        _, output = run_x("""
            function main() {
                print("".isEmpty());
                print("x".isEmpty());
                print("abc".toCharArray());
                print("héllo".toCharArray());
                print("abc".length);
                print("abc".toString());
            }
            """)
        self.assertEqual(
            output, ["true", "false", "[a, b, c]", "[h, é, l, l, o]", "3", "abc"]
        )

    def test_empty_string_edges(self):
        _, output = run_x("""
            function main() {
                print("".length);
                print("".trim());
                print("".indexOf("a"));
                print("".startsWith(""));
                print("".contains(""));
                print("".replaceAll("a", "b"));
                print("".padStart(3));
            }
            """)
        self.assertEqual(output, ["0", "", "-1", "true", "true", "", "   "])

    def test_readme_style_entry_indexing_then_upper_case(self):
        _, output = run_x("""
            function main() {
                let entry = ["name", "Ada"];
                print(entry[0].toUpperCase());
                print(entry[1].toUpperCase());
            }
            """)
        self.assertEqual(output, ["NAME", "ADA"])

    def test_no_argument_string_methods_reject_arguments(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "String.toUpperCase expects no arguments"
        ):
            run_x("""
                function main() {
                    "abc".toUpperCase(1);
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "String.trim expects no arguments"
        ):
            run_x("""
                function main() {
                    "abc".trim(1);
                }
                """)

    def test_string_argument_validation_errors(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "String.startsWith prefix must be a string"
        ):
            run_x("""
                function main() {
                    "abc".startsWith(5);
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "String.replace expects old and new string arguments"
        ):
            run_x("""
                function main() {
                    "abc".replace("a");
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "String.split separator must be a string"
        ):
            run_x("""
                function main() {
                    "abc".split(5);
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "String.indexOf part must be a string"
        ):
            run_x("""
                function main() {
                    "abc".indexOf(5);
                }
                """)

    def test_index_and_count_validation_errors(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "String.charAt index must be an integer"
        ):
            run_x("""
                function main() {
                    "abc".charAt("x");
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "String.charAt index out of bounds"
        ):
            run_x("""
                function main() {
                    "abc".charAt(5);
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "String.slice indices must be integers"
        ):
            run_x("""
                function main() {
                    "abc".slice("x");
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "String.repeat count must be a non-negative integer"
        ):
            run_x("""
                function main() {
                    "abc".repeat(-1);
                }
                """)
        with self.assertRaisesRegex(
            RuntimeErrorX, "String.padStart length must be a non-negative integer"
        ):
            run_x("""
                function main() {
                    "abc".padStart("x");
                }
                """)


if __name__ == "__main__":
    unittest.main()
