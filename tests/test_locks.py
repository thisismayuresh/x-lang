"""`System.concurrent.Lock` — reentrant lock semantics, cross-thread mutual
exclusion, tryLock timeouts, and the handle's error surface."""
import contextlib
import io
import tempfile
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from xlang.cli import main
from xlang.module_loader import ModuleLoader
from xlang.runtime import Interpreter


def run_x(source):
    """Load via ModuleLoader (resolves builtin imports) and run `main`.

    Returns (printed_output, error_or_None).
    """
    with TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory)
        source_file = project_root / "main.x"
        source_file.write_text(dedent(source), encoding="utf-8")
        output: list[str] = []
        try:
            program = ModuleLoader(project_root).load_program(source_file)
            Interpreter([], output.append).interpret(program)
            return output, None
        except Exception as exc:
            return output, str(exc)


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


class LockRuntimeTests(unittest.TestCase):
    def assertOutput(self, source, expected):
        output, error = run_x(dedent(source))
        self.assertIsNone(error, error)
        self.assertEqual(output, expected)

    def assertRuntimeError(self, source, fragment):
        output, error = run_x(dedent(source))
        self.assertIsNotNone(error, f"expected an error, got output {output}")
        self.assertIn(fragment, error)

    def test_type_of_and_initial_state(self):
        self.assertOutput(
            """
            function main() {
                let lock = System.concurrent.Lock();
                print(typeOf(lock));
                print(lock.isLocked());
            }
            """,
            ["Lock", "false"],
        )

    def test_reentrant_locking_in_one_thread(self):
        self.assertOutput(
            """
            function main() {
                let lock = System.concurrent.Lock();
                lock.lock();
                lock.lock();
                print(lock.isLocked());
                lock.unlock();
                lock.unlock();
                print(lock.isLocked());
            }
            """,
            ["true", "false"],
        )

    def test_try_lock_succeeds_on_a_free_lock(self):
        self.assertOutput(
            """
            function main() {
                let lock = System.concurrent.Lock();
                print(lock.tryLock());
                print(lock.isLocked());
                lock.unlock();
                print(lock.isLocked());
            }
            """,
            ["true", "true", "false"],
        )

    def test_unlock_without_holding_errors(self):
        self.assertRuntimeError(
            """
            function main() {
                let lock = System.concurrent.Lock();
                lock.unlock();
            }
            """,
            "does not hold",
        )

    def test_factory_rejects_arguments(self):
        self.assertRuntimeError(
            """
            function main() {
                let lock = System.concurrent.Lock(1);
            }
            """,
            "Lock() takes no arguments",
        )

    def test_unknown_method_lists_the_real_ones(self):
        self.assertRuntimeError(
            """
            function main() {
                let lock = System.concurrent.Lock();
                lock.nope();
            }
            """,
            "Lock has no method 'nope' — available methods: "
            "lock, tryLock, unlock, isLocked",
        )

    def test_try_lock_rejects_negative_timeout(self):
        self.assertRuntimeError(
            """
            function main() {
                let lock = System.concurrent.Lock();
                lock.tryLock(-5);
            }
            """,
            "cannot be negative",
        )

    def test_imported_bare_name_matches_the_qualified_path(self):
        self.assertOutput(
            """
            import System.concurrent.Lock
            function main() {
                let lock = Lock();
                lock.lock();
                lock.unlock();
                print("ok");
            }
            """,
            ["ok"],
        )

    def test_mutual_exclusion_across_threads(self):
        # Five threads each perform a read-modify-write under the lock;
        # without mutual exclusion the counter would lose updates.
        self.assertOutput(
            """
            import System.concurrent.Lock
            import System.concurrent.Thread

            let lock = Lock();
            let integer counter = 0;

            function bump() {
                lock.lock();
                let integer saved = counter;
                saved = saved + 1;
                counter = saved;
                lock.unlock();
                return 0;
            }

            function main() {
                let handles = [];
                for (integer i in range(0, 5)) {
                    handles.add(Thread.start(bump, []));
                }
                for (integer h = 0; h < 5; h = h + 1) {
                    handles[h].join();
                }
                print(counter);
                print(lock.isLocked());
            }
            """,
            ["5", "false"],
        )

    def test_try_lock_fails_while_another_thread_holds(self):
        # The holder keeps the lock for 600ms; the main thread probes at
        # ~150ms (both tryLock variants must fail) and again after join
        # (must succeed). The gaps are wide enough to absorb scheduler lag.
        self.assertOutput(
            """
            import System.concurrent.Lock
            import System.concurrent.Thread

            let lock = Lock();

            async function holder() {
                lock.lock();
                await sleep(600);
                lock.unlock();
                return 0;
            }

            async function main() {
                let handle = Thread.start(holder, []);
                await sleep(150);
                print(lock.isLocked());
                print(lock.tryLock());
                print(lock.tryLock(75));
                handle.join();
                print(lock.isLocked());
                print(lock.tryLock());
                lock.unlock();
            }
            """,
            ["true", "false", "false", "false", "true"],
        )


class LockTypeTests(unittest.TestCase):
    def test_lock_program_is_clean_under_the_checker(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "main.x"
            source_file.write_text(
                dedent(
                    """
                    import System.concurrent.Lock
                    function main() {
                        let lock = Lock();
                        lock.lock();
                        lock.tryLock();
                        print(lock.isLocked());
                        lock.unlock();
                    }
                    """
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            errors = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                return_code = main(
                    ["check", "--no-config", "--color", "never", str(source_file)]
                )
        self.assertEqual(return_code, 0, errors.getvalue())
        self.assertIn("types are valid", output.getvalue())
        self.assertEqual(errors.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
